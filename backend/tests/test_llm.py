import asyncio
import json
import logging

import httpx
import pytest

from app.config import Settings
from app.errors import LLMError
from app.llm.openrouter import OpenRouter, OpenRouterClient, make_llm, strict_schema
from app.llm.schemas import FindingsOut, SetOut

OK = '{"findings":[]}'


def answer(text, finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": finish}]})


def fail(code, message="SECRET123", headers=None, **meta):
    return httpx.Response(code, json={"error": {"code": code, "message": message, "metadata": meta}}, headers=headers or {})


class Server:
    def __init__(self, *answers, params=("structured_outputs", "response_format"), key=None, delay=0):
        self.answers, self.params, self.key, self.delay = list(answers), params, key, delay
        self.bodies, self.requests, self.now, self.peak = [], [], 0, 0

    async def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m", "supported_parameters": list(self.params)}]})
        if path.endswith("/key"):
            return self.key
        self.bodies.append(json.loads(request.content))
        self.now += 1
        self.peak = max(self.peak, self.now)
        await asyncio.sleep(self.delay)
        self.now -= 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def client(server, retries=2, **kw):
    api = OpenRouter("SECRET123", transport=httpx.MockTransport(server), **kw)
    return OpenRouterClient(api, "m", timeout=5, max_retries=retries, backoff=0)


def call(*answers, retries=2, schema=FindingsOut, **kw):
    s = Server(*answers, **kw)
    c = client(s, retries)
    return s, lambda: asyncio.run(c.generate("p", schema))


def test_ok_and_private_headers():
    s, go = call(answer(OK))
    assert go().findings == []
    r = s.requests[-1]
    assert r.headers["authorization"] == "Bearer SECRET123"
    assert "http-referer" not in r.headers and "x-title" not in r.headers


@pytest.mark.parametrize("params,kind", [(("structured_outputs", "response_format"), "json_schema"),
                                         (("response_format",), "json_object"), ((), None)])
def test_json_mode_follows_model_support(params, kind):
    s, go = call(answer(OK), params=params)
    go()
    body = s.bodies[0]
    assert body.get("response_format", {}).get("type") == kind
    assert '"findings"' in body["messages"][-1]["content"] or '"findings"' in body["messages"][0]["content"]


def test_json_in_fence_or_with_preamble():
    for text in (f"```json\n{OK}\n```", f"Вот ответ:\n{OK}", f"<think>{{}}</think>\n{OK}"):
        assert call(answer(text), params=())[1]().findings == []


def test_strict_schema_closes_every_object():
    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "object":
                assert x["additionalProperties"] is False and set(x["required"]) == set(x["properties"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(strict_schema(SetOut))


def test_retry_on_transient_and_invalid_json():
    s, go = call(fail(503), answer("не json"), answer(OK))
    go()
    assert len(s.bodies) == 3


def test_retry_limit():
    s, go = call(*[fail(503)] * 5)
    with pytest.raises(LLMError) as e:
        go()
    assert len(s.bodies) == 3 and e.value.can_switch


@pytest.mark.parametrize("code", [401, 402, 403])
def test_account_errors_stop_everything_and_key_not_leaked(code, caplog):
    caplog.set_level(logging.DEBUG)
    s, go = call(fail(code), fail(code))
    with pytest.raises(LLMError) as e:
        go()
    assert len(s.bodies) == 1 and not e.value.can_switch
    assert "SECRET123" not in str(e.value) + caplog.text


def test_moderation_403_switches_model():
    with pytest.raises(LLMError) as e:
        call(fail(403, reasons=["violence"]))[1]()
    assert e.value.can_switch


def test_daily_limit_stops_everything():
    s, go = call(*[fail(429, "Rate limit exceeded: free-models-per-day", {"X-RateLimit-Remaining": "0"})] * 3)
    with pytest.raises(LLMError, match="[Сс]уточный") as e:
        go()
    assert len(s.bodies) == 1 and not e.value.can_switch


def test_provider_429_switches_model_without_ban():
    s, go = call(*[fail(429, "Provider returned error", provider_name="x")] * 3)
    with pytest.raises(LLMError) as e:
        go()
    assert e.value.can_switch and not e.value.exhausted


def test_unknown_model_switches():
    s, go = call(fail(404))
    with pytest.raises(LLMError) as e:
        go()
    assert e.value.can_switch and e.value.exhausted and len(s.bodies) == 1


def test_rejected_response_format_falls_back_to_plain_prompt():
    s, go = call(fail(400), answer(OK))
    assert go().findings == []
    assert "response_format" in s.bodies[0] and "response_format" not in s.bodies[1]


def test_error_inside_200_is_handled():
    s, go = call(httpx.Response(200, json={"error": {"code": 502, "message": "x"}}), answer(OK))
    go()
    assert len(s.bodies) == 2


def test_truncated_and_empty_and_odd_bodies_are_errors():
    for a in (answer('{"findings":[', "length"), answer(None), httpx.Response(200, json={"choices": []}),
              httpx.Response(200, text="<html>"), httpx.Response(200, json=[]), answer(OK, "length")):
        with pytest.raises(LLMError) as e:
            call(a, retries=0)[1]()
        assert e.value.can_switch


def test_connection_error_is_transient():
    s, go = call(httpx.ConnectError("SECRET123"), answer(OK))
    go()
    assert len(s.bodies) == 2


def test_deadline():
    c = client(Server(answer(OK)))

    async def go():
        await c.generate("p", FindingsOut, deadline=asyncio.get_running_loop().time() - 1)
    with pytest.raises(LLMError, match="время"):
        asyncio.run(go())


def test_concurrency_is_shared_between_models():
    s = Server(*[answer(OK) for _ in range(10)], delay=.01)
    api = OpenRouter("k", transport=httpx.MockTransport(s), concurrency=3)
    a, b = (OpenRouterClient(api, m, 5, 0, 0) for m in ("m", "other"))

    async def go():
        await asyncio.gather(*(x.generate("p", FindingsOut) for x in (a, b) * 5))
    asyncio.run(go())
    assert s.peak == 3


def test_rate_limit_waits_for_window_and_respects_deadline():
    s = Server(*[answer(OK) for _ in range(5)])
    c = client(s, per_minute=2)

    async def go():
        d = asyncio.get_running_loop().time() + 1
        for _ in range(3):
            await c.generate("p", FindingsOut, deadline=d)
    with pytest.raises(LLMError, match="время"):
        asyncio.run(go())
    assert len(s.bodies) == 2


def key_info(**kw):
    return httpx.Response(200, json={"data": kw})


def test_preflight():
    def check(resp, need=10):
        asyncio.run(OpenRouter("SECRET123", transport=httpx.MockTransport(Server(key=resp))).preflight(need))
    check(key_info(free_model_daily_requests={"remaining": 50}))
    check(key_info())
    check(httpx.Response(503))  # справка недоступна: это не повод отменять анализ
    check(key_info(free_model_daily_requests={"remaining": 0}), need=0)
    with pytest.raises(LLMError, match="ключ"):
        check(fail(401))
    with pytest.raises(LLMError, match="осталось 3"):
        check(key_info(free_model_daily_requests={"remaining": 3}))


def test_paid_models_skip_free_quota():
    s = Settings(_env_file=None, openrouter_api_key="k", llm_model="a/b", llm_light_model="", llm_validator_model="",
                 llm_fallback_models="")
    assert make_llm(s).need == 0
    assert make_llm(s.model_copy(update={"llm_model": "a/b:free"})).need > 0
    assert make_llm(s.model_copy(update={"openrouter_api_key": ""})) is None


def test_api_survives_separate_event_loops():
    """Сервер и evaluate могут обращаться к одному клиенту из разных циклов."""
    c = client(Server(answer(OK), answer(OK)))
    asyncio.run(c.generate("p", FindingsOut))
    asyncio.run(c.generate("p", FindingsOut))
