import asyncio
import stat
import time

import pytest
from fake_llm import FakeLLM
from fastapi.testclient import TestClient
from test_api import finish, upload

from app import main
from app.pipeline import analyze
from app.store import AnalysisStore

AID = "analysis_" + "a" * 12


def entry(doc):
    r = asyncio.run(analyze(doc, FakeLLM()))
    return {"analysis_id": AID, "document_name": doc.name, "status": r.status, "stage": "", "progress": 100,
            "message": "", "created_at": "2026-11-25T10:00:00+00:00", "done": [], "active": [], "report": r}


def test_round_trip_and_permissions(tmp_path, doc):
    s = AnalysisStore(tmp_path / "d")
    a = entry(doc)
    s.save(a)
    path = tmp_path / "d" / f"{AID}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert s.load() == {AID: a}
    s.delete(AID)
    assert s.load() == {} and not list((tmp_path / "d").iterdir())


def test_broken_files_are_skipped(tmp_path, doc):
    s = AnalysisStore(tmp_path)
    s.save(entry(doc))
    (tmp_path / ("analysis_" + "b" * 12 + ".json")).write_text("{")
    (tmp_path / ("analysis_" + "c" * 12 + ".json")).write_text("[]")
    assert list(s.load()) == [AID]


@pytest.mark.parametrize("aid", ["../x", "analysis_../../etc", "", "analysis_a/b" + "a" * 9])
def test_path_traversal(tmp_path, aid):
    with pytest.raises(ValueError):
        AnalysisStore(tmp_path).delete(aid)


def start(c, text):
    did = upload(c, text).json()["document_id"]
    return c.post("/api/v1/analyses", json={"document_id": did}).json()["analysis_id"]


def test_report_survives_restart_and_delete(monkeypatch, sample_text):
    monkeypatch.setattr(main, "make_llm", lambda s: FakeLLM())
    with TestClient(main.create_app()) as c:
        aid = start(c, sample_text)
        finish(c, aid)
        before = c.get(f"/api/v1/analyses/{aid}/report").json()
    with TestClient(main.create_app()) as c:
        assert c.get(f"/api/v1/analyses/{aid}/report").json() == before
        assert c.get("/api/v1/analyses").json()[0]["analysis_id"] == aid
        assert c.delete(f"/api/v1/analyses/{aid}").status_code == 204
        assert c.delete(f"/api/v1/analyses/{aid}").status_code == 404
    with TestClient(main.create_app()) as c:
        assert c.get("/api/v1/analyses").json() == []


def test_running_analysis_cannot_be_deleted(monkeypatch, sample_text):
    class Slow(FakeLLM):
        async def generate(self, *a, **k):
            await asyncio.sleep(.2)
            return await super().generate(*a, **k)
    monkeypatch.setattr(main, "make_llm", lambda s: Slow())
    with TestClient(main.create_app()) as c:
        aid = start(c, sample_text)
        assert c.delete(f"/api/v1/analyses/{aid}").status_code == 409
        for _ in range(100):
            if c.get(f"/api/v1/analyses/{aid}").json()["status"] == "completed":
                break
            time.sleep(.05)


def test_disk_failure_does_not_lose_report(monkeypatch, sample_text):
    monkeypatch.setattr(main, "make_llm", lambda s: FakeLLM())

    def boom(self, a):
        raise OSError("диск полон")
    monkeypatch.setattr(AnalysisStore, "save", boom)
    with TestClient(main.create_app()) as c:
        aid = start(c, sample_text)
        assert finish(c, aid)["status"] == "completed"
