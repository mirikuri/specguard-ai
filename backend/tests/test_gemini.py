import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.errors import LLMError
from app.llm.gemini import Gemini, GeminiClient
from app.llm.openrouter import make_llm
from app.llm.router import ModelRouter
from app.llm.schemas import FindingsOut

OK = '{"findings":[]}'


def sse(*texts, finish="STOP", thought=None):
    chunks = []
    if thought:
        chunks.append({"candidates": [{"content": {"parts": [{"text": thought, "thought": True}]}}]})
    chunks += [{"candidates": [{"content": {"parts": [{"text": t}]}}]} for t in texts]
    chunks[-1]["candidates"][0]["finishReason"] = finish
    body = "".join(f"data: {json.dumps(c)}\r\n\r\n" for c in chunks).encode()
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def fail(code, message):
    return httpx.Response(code, json={"error": {"code": code, "message": message, "status": "X"}})


class Server:
    def __init__(self, *answers, model_status=200):
        self.answers, self.model_status = list(answers), model_status
        self.requests, self.bodies = [], []

    async def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(self.model_status, json={})
        self.bodies.append(json.loads(request.content))
        return self.answers.pop(0)


def client(server, retries=1):
    return GeminiClient(Gemini("SECRET", transport=httpx.MockTransport(server)), "gemini-x", timeout=5,
                        max_retries=retries, backoff=0)


def test_stream_is_assembled_without_thoughts():
    s = Server(sse('{"find', 'ings":[]}', thought="рассуждение"))
    assert asyncio.run(client(s).generate("p", FindingsOut)).findings == []
    r = s.requests[0]
    assert r.url.path.endswith("/models/gemini-x:streamGenerateContent") and r.url.params["alt"] == "sse"
    assert r.headers["x-goog-api-key"] == "SECRET" and "SECRET" not in str(r.url)
    cfg = s.bodies[0]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and "responseJsonSchema" in cfg and cfg["temperature"] == 0
    assert "<untrusted_document>" in s.bodies[0]["systemInstruction"]["parts"][0]["text"]


def test_rejected_schema_falls_back_to_plain_json():
    s = Server(fail(400, "Invalid JSON payload: unknown field in response_json_schema"), sse(OK))
    assert asyncio.run(client(s).generate("p", FindingsOut)).findings == []
    assert "responseJsonSchema" not in s.bodies[1]["generationConfig"]


def test_bad_key_stops_without_switching():
    s = Server(fail(400, "API key not valid. Please pass a valid API key."))
    with pytest.raises(LLMError, match="GEMINI_API_KEY") as e:
        asyncio.run(client(s).generate("p", FindingsOut))
    assert not e.value.can_switch


def test_daily_quota_exhausts_only_this_model():
    s = Server(fail(429, "Quota exceeded for metric: GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    with pytest.raises(LLMError) as e:
        asyncio.run(client(s).generate("p", FindingsOut))
    assert e.value.can_switch and e.value.exhausted


def test_minute_quota_switches_model():
    s = Server(fail(429, "Quota exceeded for metric: GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
    with pytest.raises(LLMError, match="перегружена") as e:
        asyncio.run(client(s).generate("p", FindingsOut))
    assert e.value.can_switch and not e.value.exhausted


def test_transient_error_is_retried():
    s = Server(fail(503, "overloaded"), sse(OK))
    assert asyncio.run(client(s).generate("p", FindingsOut)).findings == []


def test_cut_and_blocked_answers():
    with pytest.raises(LLMError, match="обрезан"):
        asyncio.run(client(Server(sse('{"findings":[', finish="MAX_TOKENS")), retries=0).generate("p", FindingsOut))
    with pytest.raises(LLMError, match="отказалась"):
        asyncio.run(client(Server(sse("", finish="SAFETY"))).generate("p", FindingsOut))


def test_english_answer_is_retried():
    f = {"title": "GET used for saving data", "category": "api_design", "criterion": "correct", "severity": "high",
         "confidence": .9, "evidence": [], "explanation": "The method saves the threshold but uses the GET verb.",
         "impact": "x", "recommendation": "x", "is_gap": True}
    s = Server(sse(json.dumps({"findings": [f]})), sse(OK))
    assert asyncio.run(client(s).generate("p", FindingsOut)).findings == []
    assert "не на русском" in s.bodies[1]["contents"][0]["parts"][0]["text"]


def test_preflight_reports_bad_key_and_missing_model():
    for status, text in ((400, "GEMINI_API_KEY"), (404, "GEMINI_MODEL")):
        api = Gemini("k", transport=httpx.MockTransport(Server(model_status=status)))
        api.models = ["gemini-x"]
        with pytest.raises(LLMError, match=text):
            asyncio.run(api.preflight())


def settings(**kw):
    base = dict(_env_file=None, openrouter_api_key="", gemini_api_key="", llm_model="or-main", llm_light_model="or-light",
                llm_validator_model="or-check", llm_fallback_models="", gemini_model="g-flash",
                gemini_fallback_models="g-lite", llm_provider="auto")
    return Settings(**{**base, **kw})


def test_gemini_only():
    r = make_llm(settings(gemini_api_key="g"))
    assert list(r.clients) == ["g-flash", "g-lite"] and r.roles == {"main": "g-flash", "light": "g-lite", "validator": "g-flash"}
    assert r.need == 0


def test_both_keys_openrouter_first_gemini_as_fallback():
    r = make_llm(settings(openrouter_api_key="o", gemini_api_key="g"))
    assert list(r.clients) == ["or-main", "or-check", "or-light", "g-flash", "g-lite"]
    assert r.roles["main"] == "or-main" and len(r.apis) == 2


def test_provider_gemini_goes_first():
    r = make_llm(settings(openrouter_api_key="o", gemini_api_key="g", llm_provider="gemini"))
    assert list(r.clients)[:2] == ["g-flash", "g-lite"] and r.roles["main"] == "g-flash"


def test_no_keys():
    assert make_llm(settings()) is None


class Api:
    def __init__(self, error=None):
        self.error = error

    async def preflight(self, need):
        if self.error:
            raise LLMError(self.error)


class Named:
    def __init__(self, api):
        self.api = api


def test_failed_provider_is_dropped_when_another_works():
    bad, good = Api("OpenRouter не принял ключ."), Api()
    r = ModelRouter({"a": Named(bad), "b": Named(good)}, "a", "a", "a", apis=[bad, good])
    asyncio.run(r.preflight())
    assert r._chain("main") == ["b"]


def test_all_providers_failed():
    r = ModelRouter({"a": Named(Api("нет"))}, "a", "a", "a", apis=[Api("первая"), Api("вторая")])
    with pytest.raises(LLMError, match="первая"):
        asyncio.run(r.preflight())


class Gen(Named):
    def __init__(self, api, error=None):
        super().__init__(api)
        self.error, self.calls = error, 0

    async def generate(self, prompt, schema, deadline=None):
        self.calls += 1
        if self.error:
            raise self.error
        return FindingsOut(findings=[])


def test_daily_limit_of_one_provider_moves_to_another():
    o, g = Api(), Api()
    err = LLMError("Исчерпан суточный лимит бесплатных запросов OpenRouter.", provider=True)
    a, b, c = Gen(o, err), Gen(o), Gen(g)
    r = ModelRouter({"or-a": a, "or-b": b, "g": c}, "or-a", "or-a", "or-a", apis=[o, g])
    assert asyncio.run(r.generate("p", FindingsOut)).findings == []
    assert (a.calls, b.calls, c.calls) == (1, 0, 1)  # вторую модель того же провайдера не тратим


def test_daily_limit_without_other_provider_stops():
    o = Api()
    r = ModelRouter({"or-a": Gen(o, LLMError("Исчерпан суточный лимит", provider=True)), "or-b": Gen(o)},
                    "or-a", "or-a", "or-a", apis=[o])
    with pytest.raises(LLMError, match="суточный"):
        asyncio.run(r.generate("p", FindingsOut))
