import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import CACHE_DIR, get_settings
from .errors import SpecGuardError
from .llm.cache import ResponseCache
from .llm.openrouter import make_llm
from .parser import parse_document
from .pipeline import analyze
from .reports import render

FORMATS = {".md": "md", ".html": "html", ".json": "json"}


def main(argv=None) -> int:
    """Код выхода: 0 — полный отчёт, 2 — частичный, 1 — ошибка."""
    p = argparse.ArgumentParser(prog="app.cli", description="SpecGuard AI: проверка документа с требованиями")
    p.add_argument("--input", required=True, type=Path, help="документ .md или .pdf")
    p.add_argument("--output", required=True, type=Path, help="файл отчёта .md, .html или .json")
    p.add_argument("--rules-only", action="store_true", help="только программные правила, без модели (отчёт частичный)")
    p.add_argument("--cache", action="store_true", help="отладка: повторно использовать сохранённые ответы модели")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    settings = get_settings()
    err = lambda m: print(f"Ошибка: {m}", file=sys.stderr)
    if a.output.suffix.lower() not in FORMATS:
        err("файл отчёта должен иметь расширение .md, .html или .json")
        return 1
    outputs = {fmt: a.output.with_suffix(ext) for ext, fmt in FORMATS.items()}
    if a.input.resolve() in {o.resolve() for o in outputs.values()}:
        err("отчёт не может перезаписать исходный документ")
        return 1
    try:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        doc = parse_document(a.input.name, a.input.read_bytes(), settings.max_bytes)
        llm = None if a.rules_only else make_llm(settings, ResponseCache(CACHE_DIR) if a.cache else None)
        if llm is None and not a.rules_only:
            err("не задан ключ модели в .env (OPENROUTER_API_KEY или GEMINI_API_KEY). Без модели доступен режим --rules-only (частичный отчёт).")
            return 1
        report = asyncio.run(analyze(doc, llm, timeout=settings.analysis_timeout,
                                     on_progress=lambda s, n, m: print(f"[{n:3}%] {m}", flush=True)))
        for fmt, path in outputs.items():
            path.write_text(render(report, fmt), encoding="utf-8")
    except SpecGuardError as e:
        err(e)
        return 1
    except OSError as e:
        reason = {FileNotFoundError: "файл не найден", PermissionError: "нет доступа", IsADirectoryError: "это папка, а не файл"}
        err(f"{reason.get(type(e), e.strerror)}: {e.filename}")
        return 1
    s = report.summary
    print(f"Требований: {s.requirements_count}. Подтверждено замечаний: {s.confirmed_count}. На уточнение: {s.needs_review_count}.")
    print(report.verdict.text)
    print(f"Отчёт: {a.output}")
    return 0 if report.status == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
