import asyncio
from pathlib import Path

import pytest
from fake_llm import FakeLLM

from app import cli
from app.errors import LLMError
from app.llm.schemas import AtomicOut
from app.parser import parse_document
from app.pipeline import analyze

FIXTURES = Path(__file__).parent / "fixtures"


class BadKey(FakeLLM):
    closed = False

    async def preflight(self):
        raise LLMError("ключ не принят")

    async def close(self):
        self.closed = True


def test_bad_key_stops_before_any_request(doc):
    llm = BadKey()
    with pytest.raises(LLMError, match="ключ"):
        asyncio.run(analyze(doc, llm))
    assert not llm.prompts and llm.closed


def test_cli_bad_key_writes_no_report(tmp_path, sample_text, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_llm", lambda s, cache=None: BadKey())
    src, out = tmp_path / "r.md", tmp_path / "x.md"
    src.write_text(sample_text)
    assert cli.main(["--input", str(src), "--output", str(out)]) == 1
    assert not out.exists() and "ключ не принят" in capsys.readouterr().err


def test_failed_extraction_stops_analysis(doc):
    llm = FakeLLM(fail=["ExtractionOut"])
    with pytest.raises(LLMError, match="Выделение требований"):
        asyncio.run(analyze(doc, llm))
    assert all(s.__name__ == "ExtractionOut" for s, _ in llm.prompts)


def test_batches_are_small():
    doc = parse_document("a.md", "# A\n\n".encode() + "\n\n".join(f"Ф-{i}. Клиент выполняет действие номер {i}." for i in range(1, 26)).encode())
    llm = FakeLLM()
    r = asyncio.run(analyze(doc, llm))
    assert len(r.requirements) == 25
    assert sum(s is AtomicOut for s, _ in llm.prompts) == 3


@pytest.mark.parametrize("ext", ["md", "pdf"])
def test_rules_same_in_markdown_and_pdf(ext):
    name = f"test-requirements.{ext}"
    r = asyncio.run(analyze(parse_document(name, (FIXTURES / name).read_bytes()), None))
    found = {f.rule_id: f for f in r.findings}
    assert set(found) == {"get-mutates", "template-placeholder"}
    assert "Раздел" not in found["template-placeholder"].title
    assert "TBD" in found["template-placeholder"].title
