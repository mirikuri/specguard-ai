import bisect

from ..models import Document, Evidence, Requirement, Segment

IGNORED = set("*_`|\\")
SAME = str.maketrans("“”„«»‘’–—−‑ё", "\"\"\"\"\"''----е")
MIN_FREE_QUOTE = 10  # короче — только внутри названного требования


def _normalise(text: str) -> tuple[str, list[int]]:
    chars, index = [], []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in IGNORED:
            continue
        for low in ch.translate(SAME).lower():
            chars.append(low)
            index.append(i)
    return "".join(chars), index


class EvidenceLocator:
    """Ищет цитату в документе и возвращает настоящий срез исходного текста, либо None."""

    def __init__(self, doc: Document, requirements: list[Requirement]):
        self.doc = doc
        self.norm, self.index = _normalise(doc.text)
        self.segments = doc.segments
        self.starts = [s.start for s in doc.segments]
        self.owner = {sid: r.id for r in requirements for sid in r.segment_ids}
        by_id = {s.id: s for s in doc.segments}
        self.spans = {r.id: [(by_id[s].start, by_id[s].end) for s in r.segment_ids] for r in requirements}

    def from_segment(self, seg: Segment) -> Evidence:
        return self._make(seg.start, seg.end)

    def locate(self, quote: str, requirement_id: str | None = None) -> Evidence | None:
        key, _ = _normalise(quote.strip().strip("…").strip())
        if len(key) < 2:
            return None
        for start, end in self.spans.get(requirement_id, []):
            lo, hi = bisect.bisect_left(self.index, start), bisect.bisect_left(self.index, end)
            at = self.norm.find(key, lo, hi)
            if at >= 0:
                return self._from_norm(at, len(key))
        if len(key) < MIN_FREE_QUOTE:
            return None
        at = self.norm.find(key)
        return self._from_norm(at, len(key)) if at >= 0 else None

    def _from_norm(self, at, length):
        return self._make(self.index[at], self.index[at + length - 1] + 1)

    def _make(self, start: int, end: int) -> Evidence:
        k = max(bisect.bisect_right(self.starts, start) - 1, 0)
        seg = self.segments[k]
        return Evidence(requirement_id=self.owner.get(seg.id), quote=self.doc.text[start:end], section=seg.section,
                        start=start, end=end, page=seg.page)
