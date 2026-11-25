"""Регрессии, найденные при полной перепроверке кода."""
import asyncio
import random
import time

import pytest
from fake_llm import FakeLLM, raw
from test_llm import Err, call
from test_rules import API, rules

from app.analysis.dedup import merge
from app.errors import DocumentError, LLMError
from app.models import Evidence, Finding
from app.parser import parse_document
from app.pipeline import analyze
from app.reports import render


def md(text):
    return parse_document("a.md", text.encode())


def run(d, llm, **kw):
    return asyncio.run(analyze(d, llm, **kw))


def finding(id, status="confirmed", sev="low", rule=None, req="REQ-001"):
    return Finding(id=id, title="t", category="api_design", criteria=["correct"], severity=sev, confidence=1, requirement_ids=[req],
                   evidence=[Evidence(requirement_id=req, quote="q", section="", start=0 if req == "REQ-001" else 9, end=10)], explanation="",
                   impact="", recommendation="", status=status, rule_id=rule)


# --- слияние ---

def test_unvalidated_finding_cannot_raise_confirmed_one():
    main = finding("R", rule="x")
    merge(main, finding("L", status="needs_review", sev="critical", req="REQ-002"))
    assert main.severity == "low" and main.requirement_ids == ["REQ-001"] and len(main.evidence) == 1


# --- правила: ложные срабатывания ---

@pytest.mark.parametrize("text", [
    "Поля формы заполняются автоматически из профиля клиента.",
    "Сумма перевода уточняется у клиента при подтверждении.",
])
def test_ordinary_text_is_not_placeholder(text):
    assert "template-placeholder" not in rules(f"# A\n\n{text}\n")


@pytest.mark.parametrize("text", ["TBD", "Срок: TODO", "уточняется", "заполняется позже", "будет заполнено"])
def test_real_placeholder(text):
    assert "template-placeholder" in rules(f"# A\n\n{text}\n")


def test_amount_is_not_status_code():
    t = "# A\n\n**200.** Успех.\n\nПосле успешной покупки на 250 ₸ начисляется бонус.\n"
    assert "undocumented-status" not in rules(t)


def test_get_reading_history_of_updates_is_fine():
    assert "get-mutates" not in rules(API.format(d="Просмотр истории", m="GET", u="/limits/update-history"))
    assert "get-mutates" not in rules(API.format(d="Получить обновления", m="GET", u="/limits"))


def test_same_field_in_different_methods_is_question_not_defect():
    t = ("# API\n\n## Счёт\n\n| Parameter | Format |\n|---|---|\n| `id` | integer |\n\n"
         "## Карта\n\n| Parameter | Format |\n|---|---|\n| `id` | string |\n")
    assert rules(t)["type-mismatch"].status == "needs_review"


# --- разбор ---

@pytest.mark.parametrize("text", ["Июнь 2024. Начало работ.", "HTTP 200. Успех", "RFC 9110: документ", "SHA256: алгоритм"])
def test_ordinary_start_is_not_requirement_id(text):
    assert md(f"# A\n\n{text}\n").segments[1].source_id is None


@pytest.mark.parametrize("sid", ["Ф-1", "FR-01", "REQ-1.2", "Ф1", "НФТ-12"])
def test_requirement_ids(sid):
    assert md(f"# A\n\n{sid}. Текст\n").segments[1].source_id == sid


def test_long_spaces_do_not_hang_parser():
    t = time.monotonic()
    md("# A" + " " * 100_000 + "b\n\nтекст\n")
    md("текст\n" + "- " * 50_000 + "x\n")
    md("| a\n" + "|" + " -" * 50_000 + "x\n")
    assert time.monotonic() - t < 2


def test_one_huge_paragraph_is_limited():
    with pytest.raises(DocumentError):
        run(md("# A\n\n" + "слово " * 200_000), FakeLLM())


def test_random_documents_keep_coordinates():
    rnd = random.Random(1)
    parts = ["# З", "## П", "* п", "1. ш", "| a | b |", "|---|---|", "| c | d |", "```", "текст", "", "  ", "**Ф-1.** x", "---", "😀 ё", "a | b", "> q"]
    for _ in range(3000):
        text = "\n".join(rnd.choices(parts, k=rnd.randint(1, 25)))
        try:
            d = md(text)
        except DocumentError:
            continue
        end = 0
        for s in d.segments:
            assert d.text[s.start:s.end] == s.text and s.start >= end
            end = s.end


def test_pdf_table_continued_without_header_keeps_row():
    from fpdf import FPDF
    pdf = FPDF()
    for page in (["Field", "Alpha", "Beta"], ["Gamma", "Delta"]):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        if page[0] == "Field":
            pdf.multi_cell(0, 6, "Intro text of the document.", new_x="LMARGIN", new_y="NEXT")
        with pdf.table(first_row_as_headings=False) as t:
            for c in page:
                r = t.row()
                r.cell(c)
                r.cell("value " + c)
    d = parse_document("a.pdf", bytes(pdf.output()))
    assert [s.cells[0] for s in d.segments if s.kind == "table_row"] == ["Alpha", "Beta", "Gamma", "Delta"]


# --- модель ---

def test_per_minute_limit_does_not_ban_model():
    e = Err(429)
    e.args = ("quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier",)
    with pytest.raises(LLMError) as x:
        call(e, e, e)[1]()
    assert x.value.can_switch and not x.value.exhausted


# --- конвейер ---

def contradiction():
    return raw(category="inconsistency", criterion="consistent", evidence=[
        dict(requirement_id="REQ-001", quote="Клиент задаёт порог"), dict(requirement_id="REQ-002", quote="Система быстро отправляет push")])


def test_set_check_cannot_pass_with_confirmed_contradiction(doc):
    r = run(doc, FakeLLM([contradiction()]))
    assert next(c for c in r.set_checks if c.criterion == "consistent").status == "fail"


def test_set_fail_without_any_finding_is_question():
    from app.llm.schemas import SetOut
    llm = FakeLLM([])
    llm.SetOut = lambda p: SetOut(traces=[], findings=[], checks=[dict(criterion=c, status="fail", explanation="x") for c in
                                  ("complete", "consistent", "feasible", "comprehensible", "validatable")])
    r = run(md("# A\n\n* **Ф-1.** Текст.\n* **Ф-2.** Другой.\n"), llm)
    assert {c.status for c in r.set_checks} == {"needs_review"}


def test_trace_does_not_repeat_conflict_pass(doc):
    from app.llm.schemas import ConflictsOut, SetOut
    llm = FakeLLM([])
    base = llm.SetOut("")
    llm.SetOut = lambda p: SetOut(checks=base.checks, findings=[], traces=[dict(criterion_requirement_id="REQ-001", rule_requirement_ids=["REQ-002"],
                                  calculation="", computed="", expected="", matches=False)])
    llm.ConflictsOut = lambda p: ConflictsOut(pairs=[], findings=[contradiction()])
    assert sum(f.source != "rule" for f in run(doc, llm).findings) == 1


def test_unexpected_stage_crash_is_partial_not_lost_report(doc):
    llm = FakeLLM()
    llm.FintechOut = lambda p: 1 / 0
    r = run(doc, llm)
    assert r.status == "partial" and r.findings


def test_requirement_spans_exclude_text_between_segments(doc):
    from app.llm.schemas import ExtractionOut
    ids = [s.id for s in doc.segments if s.kind != "heading"]
    llm = FakeLLM([])
    llm.ExtractionOut = lambda p: ExtractionOut(requirements=[dict(segment_ids=[ids[0], ids[-1]], summary="x", requirement_type="api", type_confidence=1)])
    q = run(doc, llm).requirements[0]
    assert "\n".join(doc.text[s:e] for s, e in q.spans) == q.text


def test_markdown_report_has_no_active_links_from_document():
    d = md("# A\n\n* **Ф-1.** ![x](http://evil.example/p.png) и [y](http://evil.example).\n")
    assert "](http" not in render(run(d, FakeLLM([])), "md")
