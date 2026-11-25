from app.analysis.scoring import DIMENSIONS, readiness
from app.models import Evidence, Finding, Requirement


def req(i, sid="Ф-1"):
    return Requirement(id=f"REQ-{i:03}", source_id=sid, summary="s", text="t", section="", source_start=0,
                       source_end=1, requirement_type="functional", type_confidence=1.0, segment_ids=[])


def finding(sev="high", status="confirmed", category="inconsistency"):
    return Finding(id="F", title="t", category=category, severity=sev, confidence=.9, requirement_ids=["REQ-001"],
                   evidence=[Evidence(requirement_id="REQ-001", quote="t", section="", start=0, end=1)],
                   explanation="", impact="", recommendation="", status=status)


ALL = set(DIMENSIONS)
REQS = [req(i) for i in range(1, 21)]


def test_clean_is_ready_100():
    r = readiness(REQS, [], ALL, "completed")
    assert (r.score, r.status) == (100, "ready")


def test_deterministic_penalty():
    r = readiness(REQS, [finding()], ALL, "completed")
    # high = 5 штрафных баллов на 20 требований -> согласованность 75 -> 100 - 0.25*25
    assert r.score == 94


def test_needs_review_not_penalised():
    assert readiness(REQS, [finding(status="needs_review")], ALL, "completed").score == 100


def test_critical_blocks():
    assert readiness(REQS * 10, [finding("critical")], ALL, "completed").status == "not_ready"


def test_unavailable_dimension_is_not_zero():
    r = readiness(REQS, [], ALL - {"consistency"}, "partial")
    assert r.score == 100 and r.coverage == 75
    assert r.status != "ready"


def test_nothing_available():
    r = readiness(REQS, [], set(), "failed")
    assert r.score is None and r.status == "not_evaluated"


def test_traceability_is_share_of_ids():
    r = readiness([req(1), req(2, None)], [], ALL, "completed")
    assert next(d for d in r.dimensions if d.id == "traceability").score == 50


def test_empty_requirements():
    assert readiness([], [], ALL, "completed").score is None
