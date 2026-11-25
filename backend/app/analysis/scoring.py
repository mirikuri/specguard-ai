from ..models import Dimension, Finding, Readiness, Requirement

# id: (название, вес)
DIMENSIONS = {
    "completeness": ("Полнота", .25), "unambiguity": ("Однозначность", .20), "testability": ("Тестируемость", .20),
    "consistency": ("Согласованность", .25), "traceability": ("Прослеживаемость", .10),
}
CATEGORY = {
    "ambiguity": "unambiguity", "non_atomic": "unambiguity", "design_constraint": "unambiguity",
    "untestable": "testability",
    "inconsistency": "consistency", "incorrect": "consistency", "redundancy": "consistency",
    "api_design": "consistency", "data_quality": "consistency",
    "traceability": "traceability",
}  # остальные категории — неполнота
CRITERION = {
    "verifiable": "testability", "validatable": "testability", "unambiguous": "unambiguity", "singular": "unambiguity",
    "comprehensible": "unambiguity", "consistent": "consistency", "correct": "consistency", "complete": "completeness",
}
PENALTY = {"critical": 10, "high": 5, "medium": 2, "low": .5, "info": 0}
MIN_REQUIREMENTS = 10  # чтобы одно замечание в маленьком документе не обнуляло оценку
MIN_COVERAGE = 50


def dimensions_of(f: Finding) -> set[str]:
    """Замечание снижает измерение своей категории и измерения нарушенных критериев, каждое один раз."""
    return {CATEGORY.get(f.category, "completeness")} | {CRITERION[c] for c in f.criteria if c in CRITERION}


def blocks(f: Finding) -> bool:
    """С такими дефектами разработку начинать нельзя: разные места документа требуют разного."""
    return f.severity == "critical" or f.severity == "high" and (
        f.category in ("inconsistency", "incorrect") or "consistent" in f.criteria and not f.is_gap)


def readiness(requirements: list[Requirement], findings: list[Finding], available: set[str], status: str) -> Readiness:
    penalty = dict.fromkeys(DIMENSIONS, 0.0)
    for f in findings:
        if f.status == "confirmed":
            for key in dimensions_of(f):
                penalty[key] += PENALTY[f.severity]
    n = max(len(requirements), MIN_REQUIREMENTS)
    dims, total, weight = [], 0.0, 0.0
    for key, (title, w) in DIMENSIONS.items():
        value = None
        if key in available and requirements:
            base = 100.0
            if key == "traceability":
                base = 100 * sum(1 for r in requirements if r.source_id) / len(requirements)
            value = max(0.0, base - 100 * penalty[key] / n)
            total, weight = total + w * value, weight + w
        dims.append(Dimension(id=key, title=title, weight=w, score=None if value is None else round(value)))
    coverage = round(weight * 100)
    if coverage < MIN_COVERAGE:
        return Readiness(score=None, status="not_evaluated", coverage=coverage, dimensions=dims)
    score = round(total / weight)
    result = "ready" if score >= 85 else "ready_with_conditions" if score >= 70 else "not_ready"
    if any(f.status == "confirmed" and blocks(f) for f in findings):
        result = "not_ready"
    elif result == "ready" and (status != "completed" or coverage < 100
                                or any(f.status == "needs_review" and blocks(f) for f in findings)):
        result = "ready_with_conditions"
    return Readiness(score=score, status=result, coverage=coverage, dimensions=dims)
