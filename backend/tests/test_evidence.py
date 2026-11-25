from app.analysis.evidence import EvidenceLocator
from app.analysis.requirements import fallback_requirements


def locator(doc):
    reqs = fallback_requirements(doc)
    return EvidenceLocator(doc, reqs), reqs


def test_exact_quote_gets_coordinates_and_owner(doc):
    loc, reqs = locator(doc)
    ev = loc.locate("Клиент задаёт порог")
    assert doc.text[ev.start:ev.end] == ev.quote == "Клиент задаёт порог"
    assert "Ф-1" in next(r for r in reqs if r.id == ev.requirement_id).source_id


def test_invented_quote_is_rejected(doc):
    assert locator(doc)[0].locate("Клиент удаляет порог") is None


def test_whitespace_and_markdown_differences_map_to_original_slice(doc):
    ev = locator(doc)[0].locate("сумму в тиынах и порог в тенге")
    assert ev.quote == "сумму в тиынах\nи порог в тенге"
    ev = locator(doc)[0].locate("REST type | GET")
    assert ev and doc.text[ev.start:ev.end] == ev.quote and "**" in ev.quote


def test_wrong_requirement_id_is_corrected_from_position(doc):
    loc, reqs = locator(doc)
    f1 = next(r for r in reqs if r.source_id == "Ф-1")
    ev = loc.locate("Клиент задаёт порог", "REQ-999")
    assert ev.requirement_id == f1.id


def test_short_ambiguous_quote_needs_its_requirement(doc):
    loc, reqs = locator(doc)
    owner = next(r for r in reqs if "REST type" in r.text)
    assert loc.locate("GET") is None
    assert loc.locate("GET", owner.id).requirement_id == owner.id


def test_empty_quote_is_rejected(doc):
    assert locator(doc)[0].locate("  ") is None
    assert locator(doc)[0].locate("** |") is None
