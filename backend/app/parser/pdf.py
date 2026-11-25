"""PDF -> Markdown-подобный текст. Координаты цитат относятся к этому тексту, номер страницы сохраняется."""
import io
import statistics

from ..errors import DocumentError


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
            pages = [_page(p, body, levels) for p in pdf.pages]
    except Exception:
        raise DocumentError("Не удалось прочитать PDF: файл повреждён или защищён паролем.") from None
    if not sizes:
        raise DocumentError("В PDF нет текстового слоя (похоже на скан). Нужен PDF с текстом или Markdown.")
    text, starts = "", []
    for page in pages:
        starts.append(len(text))
        text += page + "\n\n"
    return text, starts


def _tables(page):
    return [t for t in page.find_tables() if len(t.rows) > 1]


def _outside(tables):
    def check(obj):
        if obj["object_type"] != "char":
            return True
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in tables)
    return check


def _page(page, body, levels) -> str:
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
    for t in tables:
        rows = [[_cell(c) for c in r] for r in t.extract()]
        head, *rest = rows
        md = "\n".join(["", "| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
                       + ["| " + " | ".join(r) + " |" for r in rest]) + "\n"
        blocks.append((t.bbox[1], md))
    return "\n".join(b for _, b in sorted(blocks, key=lambda b: b[0]))
