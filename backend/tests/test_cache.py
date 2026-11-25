import asyncio

from fake_llm import FakeLLM

from app import cli
from app.errors import LLMError
from app.llm.cache import ResponseCache
from app.llm.router import ModelRouter
from app.llm.schemas import FintechOut, SetOut
from app.pipeline import analyze
from app.prompts_loader import wrap_untrusted


class Client:
    def __init__(self, error=None):
        self.calls, self.error = 0, error

    async def generate(self, prompt, schema, deadline=None):
        self.calls += 1
        if self.error:
            raise self.error
        return getattr(FakeLLM(), schema.__name__)(prompt)


def make(path, error=None):
    clients = {"main": Client(error), "spare": Client()}
    r = ModelRouter(clients, "main", "main", "main", cache=ResponseCache(path) if path else None)
    r.pause = 0
    return clients, r


def ask(r, prompt="p", schema=FintechOut):
    return asyncio.run(r.generate(prompt, schema))


def test_second_call_comes_from_disk_and_is_labelled(tmp_path):
    ask(make(tmp_path)[1])
    c, r = make(tmp_path)
    ask(r)
    assert c["main"].calls == 0 and r.used == ["main (кеш)"]


def test_random_delimiter_does_not_break_cache(tmp_path):
    c, r = make(tmp_path)
    ask(r, wrap_untrusted("текст"))
    ask(r, wrap_untrusted("текст"))
    assert c["main"].calls == 1


def test_changed_prompt_or_schema_misses(tmp_path):
    c, r = make(tmp_path)
    ask(r, "a")
    ask(r, "b")
    ask(r, "a", SetOut)
    assert c["main"].calls == 3


def test_changed_system_prompt_misses(tmp_path, monkeypatch):
    c, r = make(tmp_path)
    ask(r)
    monkeypatch.setattr("app.llm.cache.load_prompt", lambda n: "другой")
    ask(r)
    assert c["main"].calls == 2


def test_answer_of_spare_model_is_reused_without_retrying_main(tmp_path):
    busy = LLMError("503", can_switch=True)
    ask(make(tmp_path, busy)[1])
    c, r = make(tmp_path, busy)
    ask(r)
    assert c["main"].calls == 0 and r.used == ["spare (кеш)"]
    assert r.degraded == ["spare"]


def test_errors_and_broken_files_are_not_used(tmp_path):
    c, r = make(tmp_path)
    ask(r)
    for f in tmp_path.glob("*.json"):
        f.write_text("мусор")
    ask(r)
    assert c["main"].calls == 2


def test_no_cache_by_default():
    c, r = make(None)
    ask(r)
    ask(r)
    assert c["main"].calls == 2


def test_whole_repeated_analysis_needs_no_calls_and_report_says_so(tmp_path, doc):
    first = asyncio.run(analyze(doc, make(tmp_path)[1]))
    c, r = make(tmp_path)
    rep = asyncio.run(analyze(doc, r))
    assert sum(x.calls for x in c.values()) == 0
    assert "кеш" in rep.model_name and "кеш" in rep.verdict.text
    assert "кеш" not in first.model_name + first.verdict.text
    assert [f.title for f in rep.findings] == [f.title for f in first.findings]


def test_cli_flag(tmp_path, sample_text, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "make_llm", lambda s, cache=None: seen.append(cache) or FakeLLM())
    src = tmp_path / "r.md"
    src.write_text(sample_text)
    args = ["--input", str(src), "--output", str(tmp_path / "x.md")]
    cli.main(args)
    cli.main(args + ["--cache"])
    assert seen[0] is None and isinstance(seen[1], ResponseCache)
