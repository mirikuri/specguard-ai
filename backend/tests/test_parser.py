import pytest

from app.errors import DocumentError
from app.parser import parse_document


def test_every_segment_slices_exactly_from_document(doc):
    assert doc.segments
    for s in doc.segments:
        assert doc.text[s.start:s.end] == s.text
        assert s.text == s.text.strip()


def test_source_ids_are_preserved(doc):
    assert [s.source_id for s in doc.segments if s.source_id in ("Ф-1", "Ф-2")] == ["Ф-1", "Ф-2"]


def test_ordered_item_gets_id_from_section(doc):
    seg = next(s for s in doc.segments if "Проверить сессию" in s.text)
    assert seg.source_id == "Логика, п. 1"


def test_kinds_and_section_path(doc):
    row = next(s for s in doc.segments if "REST type" in s.text)
    assert row.kind == "table_row"
    assert row.section == "Лимиты по карте / REST API"
    assert row.cells == ["REST type", "GET"]
    assert row.columns == ["Поле", "Значение"]
    code = next(s for s in doc.segments if s.kind == "code")
    assert '"ERROR"' in code.text


def test_table_header_and_separator_are_not_rows(doc):
    assert not any(s.kind == "table_row" and "Значение" in s.text for s in doc.segments)
    assert not any(":---" in s.text for s in doc.segments)


def test_wrapped_paragraph_is_one_segment(doc):
    seg = next(s for s in doc.segments if "тиынах" in s.text)
    assert "порог в тенге" in seg.text


def test_heading_inside_code_is_not_heading():
    d = parse_document("a.md", "# A\n\n```sh\n# comment\n```\n\nтекст".encode())
    assert [s.text for s in d.segments if s.kind == "heading"] == ["# A"]


def test_crlf_and_bom_normalised():
    d = parse_document("a.md", "﻿# A\r\n\r\nтекст\r\n".encode())
    assert d.segments[0].kind == "heading" and "\r" not in d.text


@pytest.mark.parametrize("name,data", [
    ("a.md", b""), ("a.md", b"  \n"), ("a.docx", b"PK"),
    ("a.md", b"\xff\xfe\x00\x01"), ("a.pdf", b"not a pdf"), ("a.pdf", b"%PDF-1.4 broken"),
    ("a.md", "# только заголовок".encode()),
])
def test_bad_documents_are_rejected(name, data):
    with pytest.raises(DocumentError):
        parse_document(name, data)


def test_size_limit():
    with pytest.raises(DocumentError, match="МБ"):
        parse_document("a.md", b"a" * 100, max_bytes=50)


def make_pdf():
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=18)
    pdf.cell(0, 12, "Payments API", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, "F-1. Service stores the payment limit in KZT.")
    pdf.ln(4)
    with pdf.table() as table:
        for row in (("Field", "Value"), ("REST type", "GET")):
            r = table.row()
            for c in row:
                r.cell(c)
    pdf.add_page()
    pdf.multi_cell(0, 6, "F-2. Second page requirement.")
    return bytes(pdf.output())


def test_pdf_text_table_heading_and_pages():
    d = parse_document("a.pdf", make_pdf())
    assert d.format == "pdf"
    f1 = next(s for s in d.segments if s.source_id == "F-1")
    assert f1.page == 1 and f1.section == "Payments API"
    row = next(s for s in d.segments if s.kind == "table_row")
    assert row.cells == ["REST type", "GET"]
    assert d.text.count("REST type") == 1
    assert next(s for s in d.segments if s.source_id == "F-2").page == 2
    assert all(d.text[s.start:s.end] == s.text for s in d.segments)


def test_organizer_document(organizer_doc):
    ids = {s.source_id for s in organizer_doc.segments}
    assert {"Ф-1", "Ф-2", "Ф-3", "Ф-4"} <= ids
    assert any("Часть B" in s.section for s in organizer_doc.segments)


def test_pdf_small_table_font_does_not_turn_body_into_headings():
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.multi_cell(0, 8, "Limits", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, "F-1. Service stores the limit.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=8)
    with pdf.table() as table:
        for _ in range(8):
            r = table.row()
            r.cell("long table text that dominates the document")
            r.cell("long table text that dominates the document")
    d = parse_document("a.pdf", bytes(pdf.output()))
    f1 = next(s for s in d.segments if s.source_id == "F-1")
    assert f1.kind != "heading" and f1.section == "Limits"


def test_hard_line_break_separates_statements():
    d = parse_document("a.md", "# A\n\n**200.** Успех.  \n**400.** Ошибка.\n".encode())
    assert [s.text for s in d.segments[1:]] == ["**200.** Успех.", "**400.** Ошибка."]


def two_pages(first, second, footer=False):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(False)
    for n, lines in enumerate((first, second), 1):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in lines:
            pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
        if footer:
            pdf.set_y(-25)
            pdf.cell(0, 6, str(n), new_x="LMARGIN", new_y="NEXT")
    return parse_document("a.pdf", bytes(pdf.output()))


@pytest.mark.parametrize("footer", [False, True])
def test_pdf_sentence_split_by_page_break_is_joined(footer):
    d = two_pages(["F-1. When spending reaches the limit the client"], ["receives a push.", "F-2. Next rule."], footer)
    f1 = next(s for s in d.segments if s.source_id == "F-1")
    assert f1.text.split() == "F-1. When spending reaches the limit the client receives a push.".split()
    assert f1.page == 1 and next(s for s in d.segments if s.source_id == "F-2").page == 2
    assert all(d.text[s.start:s.end] == s.text for s in d.segments)


@pytest.mark.parametrize("first,second", [
    ("F-1. Finished sentence.", "lowercase start of another statement"),
    ("F-1. No full stop", "Second paragraph starts here"),
    ("F-1. No full stop", "F-2. Second rule"),
    ("F-1. No full stop", "- bullet item"),
])
def test_pdf_separate_statements_are_not_joined(first, second):
    d = two_pages([first], [second])
    assert next(s for s in d.segments if s.source_id == "F-1").text == first


def test_pdf_table_row_split_by_page_break_is_joined():
    from app.parser.pdf import join_pages
    text, starts = join_pages([
        "| A | B |\n| --- | --- |\n| curl | first |\n",
        "\n| A | B |\n| --- | --- |\n|  | second |\n| next | x |\n"], [False, True])
    assert "| curl | first second |" in text and "|  | second |" not in text
    assert text.count("| next | x |") == 1 and len(starts) == 2


TABLE = "| A | B |\n| --- | --- |\n"


@pytest.mark.parametrize("pages,continued,kept", [
    (["Порог\n\n1"], [False], "\n1"),
    (["Текст", "Максимум попыток\n\n2", "Конец"], [False] * 3, "\n2"),
    (["Ф-1. Клиент\n\nКонфиденциально", "получает push\n\nКонфиденциально"], [False] * 2, "Конфиденциально\n\nполучает"),
    (["specguard v1\n\nФ-1. Клиент", "specguard v1\n\nполучает push"], [False] * 2, "Клиент\n\nspecguard"),
    ([TABLE + "| Поле | Первое |\n", "\n" + TABLE + "|  | Второе |\n"], [False, True], "|  | Второе |"),
])
def test_pdf_join_keeps_unrelated_content(pages, continued, kept):
    from app.parser.pdf import join_pages
    assert kept in join_pages(pages, continued)[0]
