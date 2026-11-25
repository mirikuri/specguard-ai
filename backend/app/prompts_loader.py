import secrets
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (DIR / f"{name}.txt").read_text(encoding="utf-8")


def wrap_untrusted(text: str) -> str:
    """Случайный id не даёт документу закрыть ограничитель раньше времени."""
    tag = secrets.token_hex(8)
    return f'<untrusted_document id="{tag}">\n{text}\n</untrusted_document id="{tag}">'


def build_prompt(name: str, **parts: str) -> str:
    out = load_prompt(name)
    for key, value in parts.items():
        out += f"\n\n# {key.upper()}\n\n{value}"
    return out
