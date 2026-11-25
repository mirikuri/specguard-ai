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
