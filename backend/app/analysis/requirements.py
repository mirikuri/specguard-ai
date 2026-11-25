from ..llm.schemas import ExtractedRequirement
from ..models import Document, Requirement


def build_requirements(doc: Document, extracted: list[ExtractedRequirement]) -> list[Requirement]:
    """Модель называет только ID фрагментов; текст и координаты берутся из документа."""
    by_id = {s.id: s for s in doc.segments if s.kind != "heading"}
    used: set[str] = set()
    items = []
    for e in extracted:
        ids = [i for i in dict.fromkeys(e.segment_ids) if i in by_id and i not in used]
        if ids:
            used.update(ids)
            items.append((sorted((by_id[i] for i in ids), key=lambda s: s.start), e))
    items.sort(key=lambda x: x[0][0].start)
    return [Requirement(
        id=f"REQ-{n:03}", source_id=next((s.source_id for s in segs if s.source_id), None), summary=e.summary,
        text="\n".join(s.text for s in segs), section=segs[0].section, source_start=segs[0].start,
        source_end=segs[-1].end, spans=[(s.start, s.end) for s in segs], page=segs[0].page, requirement_type=e.requirement_type,
        type_confidence=min(max(e.type_confidence, 0), 1), segment_ids=[s.id for s in segs],
    ) for n, (segs, e) in enumerate(items, 1)]


def fallback_requirements(doc: Document) -> list[Requirement]:
    """Без модели каждый содержательный фрагмент считается требованием, тип не подтверждён."""
    return build_requirements(doc, [
        ExtractedRequirement(segment_ids=[s.id], summary=" ".join(s.text.split())[:110],
                             requirement_type="functional", type_confidence=0)
        for s in doc.segments if s.kind != "heading"])
