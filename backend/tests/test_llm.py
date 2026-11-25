import asyncio
from types import SimpleNamespace as NS

import pytest

from app.errors import LLMError
from app.llm.gemini import GeminiClient
from app.llm.schemas import FindingsOut


class Models:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    async def generate_content(self, **kw):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return NS(text=a, candidates=[])


class Err(Exception):
    def __init__(self, code):
        super().__init__("key=SECRET123")
        self.code = code


def call(*answers, retries=2):
    m = Models(*answers)
    c = GeminiClient("SECRET123", "m", max_retries=retries, min_interval=0, backoff=0, models=m)
    return m, lambda: asyncio.run(c.generate("p", FindingsOut))


def test_ok():
    m, go = call('{"findings":[]}')
    assert go().findings == []


def test_retry_on_transient_and_invalid_json():
    m, go = call(Err(429), "не json", '{"findings":[]}')
    go()
    assert m.calls == 3


def test_retry_limit_is_two():
    m, go = call(*[Err(503)] * 5)
    with pytest.raises(LLMError):
        go()
    assert m.calls == 3


def test_auth_error_not_retried_and_key_not_leaked(caplog):
    m, go = call(Err(403), Err(403))
    with pytest.raises(LLMError) as e:
        go()
    assert m.calls == 1
    assert "SECRET123" not in str(e.value) + caplog.text


def test_empty_answer_is_error():
    with pytest.raises(LLMError):
        call(None, None, None)[1]()


def test_deadline():
    c = GeminiClient("k", "m", max_retries=0, min_interval=0, backoff=0, models=Models('{"findings":[]}'))

    async def go():
        await c.generate("p", FindingsOut, deadline=asyncio.get_running_loop().time() - 1)
    with pytest.raises(LLMError, match="время"):
        asyncio.run(go())


def test_daily_quota_switches_without_retries():
    e = Err(429)
    e.args = ("quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",)
    m, go = call(e, e, e)
    with pytest.raises(LLMError) as x:
        go()
    assert m.calls == 1 and x.value.can_switch and x.value.exhausted


def test_unknown_model_can_switch():
    with pytest.raises(LLMError) as x:
        call(Err(404))[1]()
    assert x.value.can_switch and x.value.exhausted
