import re

from ..models import SEVERITY_ORDER, Finding


def _tokens(f: Finding) -> set[str]:
    return {w[:5] for w in re.findall(r"\w{3,}", f.title.lower())}


def overlaps(a: Finding, b: Finding) -> bool:
    return _shared_places(a, b) > 0


def _shared_places(a: Finding, b: Finding) -> int:
    return sum(any(x.start < y.end and y.start < x.end for y in b.evidence) for x in a.evidence)


def similar(a: Finding, b: Finding) -> bool:
    if not overlaps(a, b):
        return False
    ta, tb = _tokens(a), _tokens(b)
    close = a.category == b.category or (bool(a.rule_id) != bool(b.rule_id) and _shared_places(a, b) >= 2)
    need = 0.3 if close and a.category != b.category else 0.4 if close else 0.6
    return len(ta & tb) >= need * max(min(len(ta), len(tb)), 1)


def merge(main: Finding, extra: Finding) -> None:
    """Дополняет main доказательствами и критериями второго замечания."""
    seen = {(e.start, e.end) for e in main.evidence}
    main.evidence += [e for e in extra.evidence if (e.start, e.end) not in seen]
    main.requirement_ids = list(dict.fromkeys(main.requirement_ids + extra.requirement_ids))
    main.criteria = list(dict.fromkeys(main.criteria + extra.criteria))
    if SEVERITY_ORDER[extra.severity] < SEVERITY_ORDER[main.severity]:
        main.severity = extra.severity
    if main.source != extra.source:
        main.source = "rule+llm"
    main.confidence = max(main.confidence, extra.confidence)


def deduplicate(findings: list[Finding]) -> list[Finding]:
    out: list[Finding] = []
    for f in sorted(findings, key=lambda x: x.rule_id is None and x.source != "rule"):
        twin = next((o for o in out if f.status != "rejected" and o.status != "rejected"
                     and not (f.rule_id and o.rule_id) and similar(o, f)), None)
        if twin:
            merge(twin, f)
        else:
            out.append(f)
    return out
