from pathlib import PurePath

from ..errors import DocumentError
from ..models import Document
from .markdown import parse_markdown

MAX_BYTES = 10 * 1024 * 1024


def parse_document(name: str, data: bytes, max_bytes: int = MAX_BYTES) -> Document:
    name = PurePath(name.replace("\\", "/")).name
    suffix = PurePath(name).suffix.lower()
    if suffix not in (".md", ".markdown", ".txt", ".pdf"):
        raise DocumentError("Неподдерживаемый формат. Загрузите Markdown (.md) или PDF (.pdf).", 415)
    if len(data) > max_bytes:
        raise DocumentError(f"Файл больше {max_bytes // (1024 * 1024) or '<1'} МБ.", 413)
    if not data.strip():
        raise DocumentError("Файл пустой.")
    page_starts: list[int] = []
    if suffix == ".pdf":
        from .pdf import pdf_to_markdown
        text, page_starts = pdf_to_markdown(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DocumentError("Файл повреждён или сохранён не в UTF-8.") from None
        if "\x00" in text:
            raise DocumentError("Файл содержит двоичные данные, а не текст.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    segments = parse_markdown(text, page_starts)
    if not any(s.kind != "heading" for s in segments):
        raise DocumentError("В документе нет текста требований.")
    return Document(name=name, format="pdf" if suffix == ".pdf" else "markdown", text=text, segments=segments)
