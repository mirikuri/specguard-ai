"""Построчный разбор Markdown с точными координатами.

Обычный Markdown-парсер теряет смещения внутри строк, а цитаты должны
быть срезами исходного текста, поэтому разбор свой.
"""
import bisect
import re

from ..models import Segment

HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^ {0,3}(```+|~~~+)")
BULLET = re.compile(r"^\s*[*+\-•]\s+")
ORDERED = re.compile(r"^\s*(\d+)[.)]\s+")
RULER = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
SOURCE_ID = re.compile(r"^[\s*_`\-•+]*([A-Za-zА-Яа-яЁё]{1,6}(?:[-‑–.][A-Za-zА-Яа-яЁё]{1,6})?[-‑– ]?\d+(?:\.\d+)*)\s*(?:[.:)]|\*\*)")


def clean(s: str) -> str:
    return re.sub(r"[*_`]{1,3}(?=\S)|(?<=\S)[*_`]{1,3}", "", s).strip()


def split_row(line: str) -> list[str]:
    return [clean(c.replace("\\|", "|")) for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parse_markdown(text: str, page_starts: list[int] | None = None) -> list[Segment]:
    lines, pos = [], 0
    for raw in text.split("\n"):
        lines.append((raw, pos))
        pos += len(raw) + 1

    segments: list[Segment] = []
    path: list[tuple[int, str]] = []

    def add(kind, start, end, source_id=None, cells=(), columns=()):
        chunk = text[start:end]
        start += len(chunk) - len(chunk.lstrip())
        chunk = chunk.strip()
        if not chunk:
            return
        segments.append(Segment(
            id=f"S{len(segments) + 1:03}", kind=kind, text=chunk, start=start, end=start + len(chunk),
            section=" / ".join(t for _, t in path), source_id=source_id, cells=list(cells), columns=list(columns),
            page=bisect.bisect_right(page_starts, start) if page_starts else None))

    def end_of(k):
        return lines[k][1] + len(lines[k][0])

    def starts_block(k):
        line = lines[k][0]
        return (not line.strip() or HEADING.match(line) or FENCE.match(line) or BULLET.match(line)
                or ORDERED.match(line) or RULER.match(line) or SOURCE_ID.match(line) or is_table(k))

    def is_table(k):
        return ("|" in lines[k][0] and k + 1 < len(lines) and "|" in lines[k + 1][0]
                and bool(TABLE_SEP.match(lines[k + 1][0])))

    i = 0
    while i < len(lines):
        line, start = lines[i]
        if not line.strip() or RULER.match(line):
            i += 1
        elif m := HEADING.match(line):
            level = len(m[1])
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, clean(m[2])))
            add("heading", start, end_of(i))
            i += 1
        elif m := FENCE.match(line):
            j = i + 1
            while j < len(lines) and not lines[j][0].strip().startswith(m[1]):
                j += 1
            if j > i + 1:
                add("code", lines[i + 1][1], end_of(j - 1))
            i = j + 1
        elif is_table(i):
            columns = split_row(line)
            j = i + 2
            while j < len(lines) and "|" in lines[j][0] and lines[j][0].strip():
                cells = split_row(lines[j][0])
                if any(cells):
                    sid = SOURCE_ID.match(cells[0] + ".") if cells[0] else None
                    add("table_row", lines[j][1], end_of(j), sid[1] if sid and sid[1] == cells[0] else None, cells, columns)
                j += 1
            i = j
        else:
            j = i + 1
            while j < len(lines) and not starts_block(j) and not lines[j - 1][0].endswith("  "):
                j += 1
            kind = "list_item" if BULLET.match(line) or ORDERED.match(line) else "paragraph"
            if m := ORDERED.match(line):
                sid = f"{path[-1][1] + ', ' if path else ''}п. {m[1]}"
                if own := SOURCE_ID.match(line[m.end():]):
                    sid = own[1]
            else:
                own = SOURCE_ID.match(line)
                sid = own[1] if own else None
            add(kind, start, end_of(j - 1), sid)
            i = j
    return segments
