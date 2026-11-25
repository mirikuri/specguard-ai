import asyncio

import pytest
from fake_llm import FakeLLM

from app.config import Settings
from app.errors import LLMError
from app.llm.gemini import make_llm
from app.llm.router import ModelRouter
from app.llm.schemas import AtomicOut, ExtractionOut, FintechOut, ValidationOut
from app.pipeline import analyze


class Client:
    def __init__(self, model, error=None):
        self.model, self.error, self.calls = model, error, 0

    async def generate(self, prompt, schema, deadline=None):
        self.calls += 1
        if self.error:
            raise self.error
        return getattr(FakeLLM(), schema.__name__)(prompt)


def router(**errors):
    clients = {m: Client(m, errors.get(m)) for m in ("main", "light", "check", "spare")}
    r = ModelRouter(clients, main="main", light="light", validator="check")
    r.pause = 0
    return clients, r


def ask(r, schema):
    return asyncio.run(r.generate("p", schema))


def test_stages_use_their_models():
    c, r = router()
    for s in (ExtractionOut, FintechOut, ValidationOut):
        ask(r, s)
    assert r.used == ["light", "main", "check"]


def test_fallback_on_quota_and_exhausted_model_not_retried():
    c, r = router(main=LLMError("429", can_switch=True, exhausted=True))
    ask(r, FintechOut)
    ask(r, FintechOut)
    assert c["main"].calls == 1 and "main" not in r.used and len(r.used) == 2


def test_overloaded_model_goes_last_but_is_not_banned():
    c, r = router(main=LLMError("503", can_switch=True))
    ask(r, FintechOut)
    ask(r, FintechOut)
    assert c["main"].calls == 1
    for m in ("light", "check", "spare"):
        c[m].error = LLMError("503", can_switch=True)
    c["main"].error = None
    ask(r, FintechOut)
    assert r.used[-1] == "main"


def test_overloaded_model_returns_after_cooldown():
    c, r = router(main=LLMError("503", can_switch=True))
    r.cooldown = 0
    ask(r, FintechOut)
    ask(r, FintechOut)
    assert c["main"].calls == 2


def test_bad_key_is_not_tried_on_every_model():
    c, r = router(main=LLMError("403"))
    with pytest.raises(LLMError):
        ask(r, FintechOut)
    assert sum(x.calls for x in c.values()) == 1


def test_validator_avoids_model_that_found_problems():
    c, r = router(main=LLMError("429", can_switch=True, exhausted=True),
                  light=LLMError("429", can_switch=True, exhausted=True))
    ask(r, AtomicOut)
    assert r.used == ["check"]
    ask(r, ValidationOut)
    assert r.used[-1] == "spare"


def test_all_exhausted():
    c, r = router(**{m: LLMError("429", can_switch=True, exhausted=True) for m in ("main", "light", "check", "spare")})
    for _ in range(2):
        with pytest.raises(LLMError):
            ask(r, FintechOut)


def test_report_names_models_really_used(doc):
    c, r = router()
    rep = asyncio.run(analyze(doc, r))
    assert rep.status == "completed"
    assert all(m in rep.model_name for m in ("main", "light", "check")) and "spare" not in rep.model_name
    assert next(s for s in rep.stages if s.id == "evidence_validation").models[0] == "check"


def test_make_llm_builds_unique_chain():
    s = Settings(_env_file=None, gemini_api_key="k", gemini_model="a", gemini_light_model="b",
                 gemini_validator_model="a", gemini_fallback_models="b, c")
    assert list(make_llm(s).clients) == ["a", "b", "c"]


def test_finder_prefers_strong_validator_model_over_light():
    s = Settings(_env_file=None, gemini_api_key="k", gemini_model="a", gemini_light_model="lite",
                 gemini_validator_model="strong", gemini_fallback_models="")
    assert make_llm(s)._chain("main") == ["a", "strong", "lite"]


def test_second_sweep_after_overload():
    c, r = router(**{m: LLMError("503", can_switch=True) for m in ("main", "light", "check", "spare")})
    r.pause = 0
    n = 0
    original = c["main"].generate

    async def recover(*a, **k):
        nonlocal n
        n += 1
        c["main"].error = None if n > 1 else LLMError("503", can_switch=True)
        return await original(*a, **k)
    c["main"].generate = recover
    ask(r, FintechOut)
    assert r.used == ["main"]


def test_report_warns_when_weaker_models_did_the_search(doc):
    dead = LLMError("429", can_switch=True, exhausted=True)
    c, r = router(main=dead, check=dead)
    rep = asyncio.run(analyze(doc, r))
    assert "запасн" in rep.verdict.text
    assert rep.readiness.status != "ready"
    _, ok = router()
    assert "запасн" not in asyncio.run(analyze(doc, ok)).verdict.text
