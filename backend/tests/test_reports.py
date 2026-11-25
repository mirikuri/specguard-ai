import asyncio
import json

from app.parser import parse_document
from app.pipeline import analyze
from app.reports import render
from fake_llm import FakeLLM, raw


def report(doc, **kw):
    return asyncio.run(analyze(doc, FakeLLM(**kw)))


def test_markdown_has_all_organizer_sections(doc):
    md = render(report(doc), "md")
    for h in ("Паспорт прогона", "Как агент нарезал требования", "Проверка каждого требования",
              "Проверка всего набора", "Сводка", "Итог"):
        assert f"## " in md and h in md
    assert "fake" in md and "REQ-001" in md and "Ф-1" in md
    assert "Система быстро отправляет push" in md


def test_partial_is_loud(doc):
    assert "ЧАСТИЧН" in render(report(doc, fail=["AtomicOut"]), "md").upper()


def test_json_roundtrip(doc):
    assert json.loads(render(report(doc), "json"))["status"] == "completed"


def test_html_escapes_document():
    d = parse_document("a.md", "# A\n\n* **Ф-1.** Текст.\n* **Ф-2.** <script>alert(1)</script> быстро\n".encode())
    html = render(report(d, findings=[raw(quote="<script>alert(1)</script>")]), "html")
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_markdown_table_cells_escaped():
    d = parse_document("a.md", "# A\n\n* **Ф-1.** a | b.\n* **Ф-2.** <img src=x> в\n".encode())
    md = render(report(d, findings=[]), "md")
    row = next(l for l in md.splitlines() if l.startswith("| REQ-001"))
    assert row.count("|") - row.count("\\|") == 5
    assert "<img" not in md


def conflict():
    return raw(title="Правила расходятся", category="inconsistency", criterion="consistent", evidence=[
        dict(requirement_id="REQ-001", quote="Клиент задаёт порог"),
        dict(requirement_id="REQ-002", quote="Система быстро отправляет push")])


def test_questions_go_before_requirements_and_critical_list_has_open_conflict(doc):
    r = report(doc, findings=[conflict()], verdict="needs_review")
    for fmt in ("md", "html"):
        out = render(r, fmt)
        assert out.index("Вопросы аналитику") < out.index("Как агент нарезал")
        assert "Q-01" in out
        assert "Правила расходятся (требует решения)" in out


def test_old_saved_report_without_questions_still_loads(doc):
    from app.models import AnalysisReport
    data = json.loads(render(report(doc), "json"))
    del data["questions"]
    assert AnalysisReport.model_validate(data).questions == []
