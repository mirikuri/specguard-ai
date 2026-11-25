from app.analysis.dedup import deduplicate
from app.models import Evidence, Finding


def f(id, title, start=0, end=20, cat="api_design", source="llm", sev="high", status="confirmed"):
    return Finding(id=id, title=title, category=cat, severity=sev, confidence=.8, requirement_ids=["REQ-001"],
                   evidence=[Evidence(requirement_id="REQ-001", quote="q", section="", start=start, end=end)],
                   explanation="", impact="", recommendation="", status=status, source=source)


def test_same_problem_merged_rule_wins():
    out = deduplicate([f("A", "Метод GET сохраняет настройки"), f("B", "GET используется для сохранения настроек", source="rule", sev="medium")])
    assert len(out) == 1
    assert out[0].source == "rule+llm" and out[0].severity == "high"


def test_different_problem_same_place_kept():
    assert len(deduplicate([f("A", "Метод GET сохраняет настройки"), f("B", "Не указан формат идентификатора карты")])) == 2


def test_same_title_other_place_kept():
    assert len(deduplicate([f("A", "Нет единиц"), f("B", "Нет единиц", 100, 120)])) == 2


def test_rejected_does_not_merge_into_confirmed():
    out = deduplicate([f("A", "Метод GET сохраняет", status="rejected"), f("B", "Метод GET сохраняет")])
    assert {x.status for x in out} == {"confirmed", "rejected"}


def test_rule_and_llm_sharing_two_places_merge_across_categories():
    def two(x):
        x.evidence.append(Evidence(requirement_id="REQ-002", quote="q", section="", start=50, end=70))
        return x
    a = two(f("A", "Метод GET используется для изменения данных", source="rule"))
    a.rule_id = "get-mutates"
    b = two(f("B", "Несоответствие семантики метода GET принципам REST", cat="ambiguity"))
    assert len(deduplicate([a, b])) == 1
