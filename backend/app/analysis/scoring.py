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
PENALTY = {"critical": 10, "high": 5, "medium": 2, "low": .5, "info": 0}
MIN_REQUIREMENTS = 10  # чтобы одно замечание в маленьком документе не обнуляло оценку
MIN_COVERAGE = 50


def readiness(requirements: list[Requirement], findings: list[Finding], available: set[str], status: str) -> Readiness:
    penalty = dict.fromkeys(DIMENSIONS, 0.0)
    for f in findings:
        if f.status == "confirmed":
            penalty[CATEGORY.get(f.category, "completeness")] += PENALTY[f.severity]
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
    if any(f.status == "confirmed" and f.severity == "critical" for f in findings):
        result = "not_ready"
    elif result == "ready" and (status != "completed" or coverage < 100):
        result = "ready_with_conditions"
    return Readiness(score=score, status=result, coverage=coverage, dimensions=dims)
