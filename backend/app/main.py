import asyncio
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import DATA_DIR, ROOT, agent_version, get_settings
from .errors import DocumentError, SpecGuardError
from .llm.openrouter import make_llm
from .models import AnalysisOptions
from .parser import parse_document
from .pipeline import STAGES, analyze
from .reports import MEDIA, render
from .store import AnalysisStore

log = logging.getLogger("specguard.api")
DIST = ROOT / "frontend" / "dist"
MAX_STORED = 30


class AnalysisRequest(BaseModel):
    document_id: str
    language: Literal["ru"] = "ru"
    analysis_profile: Literal["fintech"] = "fintech"
    options: AnalysisOptions = AnalysisOptions()
    rules_only: bool = False


def put(store: dict, key: str, value) -> None:
    store[key] = value
    for old in list(store)[:-MAX_STORED]:
        if store[old].get("status") not in ("queued", "running"):
            del store[old]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SpecGuard AI", version=settings.agent_version, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", settings.backend_host])
    documents: dict[str, dict] = {}
    store = AnalysisStore(DATA_DIR)
    analyses: dict[str, dict] = store.load()
    tasks: set[asyncio.Task] = set()
    api = APIRouter(prefix="/api/v1")

    @app.exception_handler(DocumentError)
    async def document_error(_: Request, e: DocumentError):
        return JSONResponse({"detail": str(e)}, e.status)

    def doc_info(did):
        d = documents[did]
        return {"document_id": did, "filename": d["doc"].name, "size": d["size"], "format": d["doc"].format, "status": "uploaded"}

    def get_analysis(aid):
        if aid not in analyses:
            raise HTTPException(404, "Проверка не найдена.")
        return analyses[aid]

    def info(a):
        out = {k: a[k] for k in ("analysis_id", "document_name", "status", "stage", "progress", "message", "created_at", "done", "active")}
        if r := a["report"]:
            out |= {"score": r.readiness.score, "readiness_status": r.readiness.status,
                    "findings_count": r.summary.findings_count, "requirements_count": r.summary.requirements_count}
        return out

    @api.get("/health")
    async def health():
        return {"status": "ok", "version": agent_version(), "model": settings.llm_model, "model_ready": make_llm(settings) is not None,
                "stages": [{"id": i, "title": t} for i, t, _ in STAGES]}

    @api.post("/documents", status_code=201)
    async def upload(file: UploadFile):
        data = await file.read(settings.max_bytes + 1)
        doc = await asyncio.to_thread(parse_document, file.filename or "", data, settings.max_bytes)
        did = "doc_" + secrets.token_urlsafe(9)
        put(documents, did, {"doc": doc, "size": len(data)})
        return doc_info(did)

    @api.get("/documents/{did}")
    async def document(did: str):
        if did not in documents:
            raise HTTPException(404, "Документ не найден.")
        return doc_info(did)

    async def work(a, doc, llm, options):
        def progress(stage, percent, message):
            a["active"].append(stage)
            a.update(status="running", stage=stage, progress=percent, message=message)
        def done(stage):
            a["active"].remove(stage)
            a["done"].append(stage)

        try:
            report = await analyze(doc, llm, options, progress, settings.analysis_timeout, done)
            ready = dict(report=report, status=report.status, stage="", progress=100, message="Отчёт готов")
            try:
                await asyncio.to_thread(store.save, {**a, **ready})
            except OSError:
                log.exception("Отчёт не сохранён на диск")
            a.update(ready)
        except SpecGuardError as e:
            a.update(status="failed", message=str(e))
        except Exception:
            log.exception("Сбой анализа")
            a.update(status="failed", message="Внутренняя ошибка анализа. Подробности в журнале сервера.")

    @api.post("/analyses", status_code=202)
    async def start(body: AnalysisRequest):
        if body.document_id not in documents:
            raise HTTPException(404, "Документ не найден. Загрузите его ещё раз.")
        llm = None if body.rules_only else make_llm(settings)
        if llm is None and not body.rules_only:
            raise HTTPException(503, "Модель не подключена: администратору нужно задать OPENROUTER_API_KEY.")
        doc = documents[body.document_id]["doc"]
        aid = "analysis_" + secrets.token_urlsafe(9)
        a = {"analysis_id": aid, "document_name": doc.name, "status": "queued", "stage": "", "progress": 0, "message": "В очереди",
             "done": [], "active": [], "created_at": datetime.now(timezone.utc).isoformat(), "report": None}
        analyses[aid] = a
        task = asyncio.create_task(work(a, doc, llm, body.options))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return {"analysis_id": aid, "status": "queued"}

    @api.get("/analyses")
    async def recent():
        return [info(a) for a in reversed(analyses.values())]

    @api.get("/analyses/{aid}")
    async def status(aid: str):
        return info(get_analysis(aid))

    @api.delete("/analyses/{aid}", status_code=204)
    async def delete(aid: str):
        if get_analysis(aid)["status"] in ("queued", "running"):
            raise HTTPException(409, "Проверка ещё идёт.")
        store.delete(aid)
        del analyses[aid]

    def ready_report(aid):
        a = get_analysis(aid)
        if a["report"] is None:
            raise HTTPException(409, a["message"] if a["status"] == "failed" else "Анализ ещё не завершён.")
        return a["report"]

    @api.get("/analyses/{aid}/report")
    async def report(aid: str):
        return ready_report(aid)

    @api.get("/analyses/{aid}/export")
    async def export(aid: str, format: Literal["html", "json", "md"]):
        r = ready_report(aid)
        name = quote(f"specguard-{Path(r.document_name).stem}.{format}")
        return Response(render(r, format), media_type=MEDIA[format] + "; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}", "X-Content-Type-Options": "nosniff"})

    app.include_router(api)

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Не найдено.")
        target = (DIST / path).resolve()
        if path and target.is_relative_to(DIST) and target.is_file():
            return FileResponse(target)
        if (DIST / "index.html").is_file():
            return FileResponse(DIST / "index.html")
        raise HTTPException(404, "Интерфейс не собран: выполните npm ci && npm run build в каталоге frontend.")

    return app


def run():
    import uvicorn
    s = get_settings()
    uvicorn.run(create_app(), host=s.backend_host, port=s.backend_port)


if __name__ == "__main__":
    run()
