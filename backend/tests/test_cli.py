import json

from app import cli
from fake_llm import FakeLLM


def test_cli_writes_reports(tmp_path, sample_text, monkeypatch):
    monkeypatch.setattr(cli, "make_llm", lambda s: FakeLLM())
    src, out = tmp_path / "r.md", tmp_path / "o" / "report.md"
    src.write_text(sample_text)
    assert cli.main(["--input", str(src), "--output", str(out)]) == 0
    assert "Паспорт" in out.read_text()
    assert json.loads(out.with_suffix(".json").read_text())["document_name"] == "r.md"
    assert out.with_suffix(".html").exists()


def test_cli_partial_exit_code(tmp_path, sample_text, monkeypatch):
    monkeypatch.setattr(cli, "make_llm", lambda s: FakeLLM(fail=["AtomicOut"]))
    src = tmp_path / "r.md"
    src.write_text(sample_text)
    assert cli.main(["--input", str(src), "--output", str(tmp_path / "x.md")]) == 2


def test_cli_missing_file(tmp_path):
    assert cli.main(["--input", str(tmp_path / "no.md"), "--output", str(tmp_path / "x.md")]) == 1


def test_cli_without_key_refuses_unless_rules_only(tmp_path, sample_text, monkeypatch):
    monkeypatch.setattr(cli, "make_llm", lambda s: None)
    src, out = tmp_path / "r.md", tmp_path / "x.md"
    src.write_text(sample_text)
    assert cli.main(["--input", str(src), "--output", str(out)]) == 1
    assert not out.exists()
    assert cli.main(["--input", str(src), "--output", str(out), "--rules-only"]) == 2


def test_cli_never_overwrites_input(tmp_path, sample_text, monkeypatch):
    monkeypatch.setattr(cli, "make_llm", lambda s: FakeLLM())
    src = tmp_path / "r.md"
    src.write_text(sample_text)
    assert cli.main(["--input", str(src), "--output", str(src)]) == 1
    assert src.read_text() == sample_text
