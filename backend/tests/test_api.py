import time

import pytest
from fastapi.testclient import TestClient

from app import main
from fake_llm import FakeLLM


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "make_llm", lambda s: FakeLLM())
    with TestClient(main.create_app()) as c:
        yield c


def upload(c, text, name="r.md"):
    return c.post("/api/v1/documents", files={"file": (name, text.encode())})


def finish(c, aid):
    for _ in range(100):
        s = c.get(f"/api/v1/analyses/{aid}").json()
        if s["status"] in ("completed", "partial", "failed"):
            return s
        time.sleep(.02)
    raise AssertionError("не завершился")


def test_scenario(client, sample_text):
    r = upload(client, sample_text)
    assert r.status_code == 201
    did = r.json()["document_id"]
    assert client.get(f"/api/v1/documents/{did}").json()["filename"] == "r.md"
    a = client.post("/api/v1/analyses", json={"document_id": did})
    assert a.status_code == 202
    aid = a.json()["analysis_id"]
    s = finish(client, aid)
    assert s["status"] == "completed" and s["progress"] == 100
    rep = client.get(f"/api/v1/analyses/{aid}/report").json()
    assert rep["summary"]["requirements_count"] == len(rep["requirements"])
    assert rep["readiness"]["score"] is not None and rep["document_text"]
    for fmt in ("html", "json", "md"):
        e = client.get(f"/api/v1/analyses/{aid}/export", params={"format": fmt})
        assert e.status_code == 200 and "attachment" in e.headers["content-disposition"]
    assert client.get("/api/v1/analyses").json()[0]["analysis_id"] == aid


def test_bad_upload(client):
    r = upload(client, "x", "a.exe")
    assert r.status_code == 415 and "Markdown" in r.json()["detail"]
    assert upload(client, "").status_code == 422


def test_too_big(client):
    assert upload(client, "a" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_unknown_ids(client):
    assert client.get("/api/v1/analyses/x").status_code == 404
    assert client.get("/api/v1/documents/x").status_code == 404
    assert client.post("/api/v1/analyses", json={"document_id": "x"}).status_code == 404


def test_health_and_bad_format(client):
    h = client.get("/api/v1/health").json()
    assert h["status"] == "ok" and "key" not in str(h).lower()
    assert client.get("/api/v1/analyses/x/export?format=exe").status_code == 422


def test_no_key(monkeypatch, sample_text):
    monkeypatch.setattr(main, "make_llm", lambda s: None)
    with TestClient(main.create_app()) as c:
        did = upload(c, sample_text).json()["document_id"]
        r = c.post("/api/v1/analyses", json={"document_id": did})
        assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]
        r = c.post("/api/v1/analyses", json={"document_id": did, "rules_only": True})
        assert finish(c, r.json()["analysis_id"])["status"] == "partial"


def test_foreign_host_rejected(client):
    assert client.get("/api/v1/health", headers={"host": "evil.example"}).status_code == 400
