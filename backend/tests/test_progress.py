import asyncio
import time

import pytest
from fake_llm import FakeLLM
from fastapi.testclient import TestClient
from test_api import finish, upload
from test_llm import Server, answer, client, fail, OK
from test_router import Client

from app import main
from app.errors import LLMError
from app.llm.router import ModelRouter
from app.llm.schemas import ExtractionOut, FindingsOut
from app.pipeline import analyze


def events_of(doc, llm):
    out = []
    asyncio.run(analyze(doc, llm, on_event=lambda kind, text: out.append((kind, text))))
    return out


def test_events_tell_what_happens(doc):
    ev = events_of(doc, FakeLLM())
    text = "\n".join(t for _, t in ev)
    for part in ("Документ прочитан", "Выделено требований", "Проверено требований", "Подтверждено"):
        assert part in text, part
    assert any(k == "finding" and "Не задано время отправки" in t for k, t in ev)


def test_failed_stage_is_told(doc):
    assert any(k == "error" and "Исправления" in t for k, t in events_of(doc, FakeLLM(fail=["FixesOut"])))


def test_model_switch_is_told(doc):
    clients = {"main": Client("main", LLMError("429", can_switch=True)), "spare": Client("spare")}
    ev = events_of(doc, ModelRouter(clients, "main", "main", "main"))
    assert any(k == "warn" and "другой" in t for k, t in ev)


class Slow(FakeLLM):
    async def generate(self, *a, **k):
        await asyncio.sleep(30)


def test_status_has_log_and_cancel_works(monkeypatch, sample_text):
    monkeypatch.setattr(main, "make_llm", lambda s: Slow())
    with TestClient(main.create_app()) as c:
        did = upload(c, sample_text).json()["document_id"]
        aid = c.post("/api/v1/analyses", json={"document_id": did}).json()["analysis_id"]
        for _ in range(50):
            s = c.get(f"/api/v1/analyses/{aid}").json()
            if s["events"]:
                break
            time.sleep(.02)
        assert s["events"][0]["text"] and s["events"][0]["time"]
        assert "requirements_extraction" in s["started"]
        assert "events" not in c.get("/api/v1/analyses").json()[0]
        assert c.post(f"/api/v1/analyses/{aid}/cancel").status_code == 202
        s = finish(c, aid)
        assert s["status"] == "failed" and "Отменено" in s["message"]
        assert c.post(f"/api/v1/analyses/{aid}/cancel").status_code == 409
        assert c.delete(f"/api/v1/analyses/{aid}").status_code == 204


def test_mechanical_steps_skip_reasoning():
    for schema, off in ((ExtractionOut, True), (FindingsOut, False)):
        s = Server(answer('{"requirements":[]}' if off else OK), params=("reasoning",))
        asyncio.run(client(s).generate("p", schema))
        assert ("reasoning" in s.bodies[0]) is off


def test_overloaded_model_is_not_retried():
    s = Server(*[fail(429, "Provider returned error")] * 3)
    with pytest.raises(LLMError) as e:
        asyncio.run(client(s).generate("p", FindingsOut))
    assert len(s.bodies) == 1 and e.value.can_switch
