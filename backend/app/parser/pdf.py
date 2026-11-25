"""PDF -> Markdown-подобный текст. Координаты цитат относятся к этому тексту, номер страницы сохраняется."""
import io
import re
import statistics

from ..errors import DocumentError
from .markdown import BULLET, HEADING, ORDERED, SOURCE_ID


def _cell(value) -> str:
    return " ".join((value or "").split()).replace("|", "\\|")


def pdf_to_markdown(data: bytes) -> tuple[str, list[int]]:
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            sizes = [round(c["size"], 1) for p in pdf.pages for c in p.chars if c["text"].strip()]
            # таблицы часто набраны мельче и искажают размер основного текста
            prose = [round(c["size"], 1) for p in pdf.pages for c in p.filter(_outside(_tables(p))).chars if c["text"].strip()]
            body = statistics.mode(prose or sizes or [0])
            levels = sorted({s for s in prose if s >= body * 1.12}, reverse=True)
            pages, continued, previous = [], [], None
            for p in pdf.pages:
                text, previous, cont = _page(p, body, levels, previous)
                pages.append(text)
                continued.append(cont)
    except Exception:
        raise DocumentError("Не удалось прочитать PDF: файл повреждён или защищён паролем.") from None
    if not sizes:
        raise DocumentError("В PDF нет текстового слоя (похоже на скан). Нужен PDF с текстом или Markdown.")
    return join_pages(pages, continued)


def join_pages(pages: list[str], continued: list[bool]) -> tuple[str, list[int]]:
    """Склеивает предложение и строку таблицы, разорванные границей страницы.

    continued[n] — страница n начинается продолжением таблицы прошлой страницы."""
    pages = _drop_page_numbers(pages)
    edges = [(_first(p), _last(p)) for p in pages if p.strip()]
    text, starts = "", []
    for n, page in enumerate(pages):
        if n and continued[n]:
            text, page = _join_row(text, page)
        first, last = _first(page), _last(text)
        running = sum(first == f for f, _ in edges) > 1 or sum(last == x for _, x in edges) > 1  # колонтитул
        if n and not running and _splits_sentence(last, first):
            text, page = text.rstrip("\n") + "\n", page.lstrip("\n")
        starts.append(len(text))
        text += page + "\n\n"
    return text, starts


def _first(text: str) -> str:
    return text.strip("\n").partition("\n")[0].strip()


def _last(text: str) -> str:
    return text.strip("\n").rpartition("\n")[2].strip()


def _drop_page_numbers(pages: list[str]) -> list[str]:
    """Номера внизу убираем, только если они стоят на всех страницах (кроме, возможно, обложки):
    одиночное число в конце страницы может быть значением требования."""
    numbered = [_last(p) == str(n) for n, p in enumerate(pages, 1)]
    if len(pages) < 2 or not all(numbered[1:]) or (len(pages) == 2 and not numbered[0]):
        return pages
    return [p.rstrip("\n").rpartition("\n")[0] if hit else p for p, hit in zip(pages, numbered)]


def _splits_sentence(last: str, first: str) -> bool:
    if not last or last[-1] in ".!?;:|`" or HEADING.match(last) or not first[:1].islower():
        return False
    return not any(p.match(first) for p in (BULLET, ORDERED, SOURCE_ID)) and "|" not in first


def _join_row(before: str, page: str) -> tuple[str, str]:
    """Пустая первая ячейка сразу после границы страницы — остаток прошлой строки."""
    lines = page.split("\n")
    k = next((i + 1 for i, line in enumerate(lines) if line.startswith("| ---")), len(lines))
    table, _, last = before.rstrip("\n").rpartition("\n")
    if k >= len(lines) or not lines[k].startswith("|  |") or not last.startswith("| "):
        return before, page
    tail, head = split_cells(lines[k]), split_cells(last)
    # с заглавной или после точки — новая строка под объединённой ячейкой, а не остаток старой
    if len(tail) != len(head) or any(t and (not h or t[0].isupper() or h[-1] in ".!?;") for t, h in zip(tail, head)):
        return before, page
    row = "| " + " | ".join(f"{h} {t}".strip() for h, t in zip(head, tail)) + " |"
    del lines[k]
    return f"{table}\n{row}\n\n\n", "\n".join(lines)


def split_cells(line: str) -> list[str]:
    """Ячейки без снятия разметки, в отличие от split_row."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def _tables(page):
    return [t for t in page.find_tables() if len(t.rows) > 1]


def _outside(tables):
    def check(obj):
        if obj["object_type"] != "char":
            return True
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in tables)
    return check


def _page(page, body, levels, previous=None):
    """previous — шапка таблицы, которой закончилась прошлая страница."""
    tables = _tables(page)
    blocks = []
    prev_bottom = None
    for line in page.filter(_outside(tables)).extract_text_lines():
        text = line["text"].strip()
        if not text:
            continue
        size = statistics.median(c["size"] for c in line["chars"])
        level = next((i for i, s in enumerate(levels) if size >= s - 0.15), None)
        if level is not None and len(text) < 160 and text[-1] not in ".;,":
            text = "#" * min(level + 1, 6) + " " + text + "\n"
        gap = prev_bottom is not None and line["top"] - prev_bottom > size * 0.9
        blocks.append((line["top"], ("\n" if gap else "") + text))
        prev_bottom = line["bottom"]
    tops = [top for top, _ in blocks]
    last_header, cont = None, False
    for n, t in enumerate(tables):
        rows = [[_cell(c) for c in r] for r in t.extract()]
        head, *rest = rows
        # продолжение таблицы с прошлой страницы: первая строка — данные, а не шапка (допускаем один колонтитул)
        if n == 0 and previous and len(previous) == len(head) and sum(top < t.bbox[1] for top in tops) <= 1:
            cont = not any(top < t.bbox[1] for top in tops)
            rest = rest if head == previous else rows
            head = previous
        if n == len(tables) - 1 and sum(top > t.bbox[3] for top in tops) <= 1:
            last_header = head
        md = "\n".join(["", "| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
                       + ["| " + " | ".join(r) + " |" for r in rest]) + "\n"
        blocks.append((t.bbox[1], md))
    return "\n".join(b for _, b in sorted(blocks, key=lambda b: b[0])), last_header, cont
