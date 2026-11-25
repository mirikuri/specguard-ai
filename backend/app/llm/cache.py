"""Кеш ответов модели для отладки. Включается только явно, ответы из кеша помечаются в отчёте."""
import hashlib
import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ..prompts_loader import load_prompt

DELIMITER = re.compile(r'(untrusted_document id=")[0-9a-f]{16}(")')


class ResponseCache:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, model: str, prompt: str, schema: type[BaseModel]) -> Path:
        # случайный id ограничителя меняется в каждом запросе и на ответ не влияет
        key = [model, load_prompt("system"), DELIMITER.sub(r"\1\2", prompt), schema.model_json_schema()]
        return self.directory / (hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest() + ".json")

    def get(self, model, prompt, schema):
        try:
            return schema.model_validate_json(self._path(model, prompt, schema).read_text(encoding="utf-8"))
        except (OSError, ValidationError, UnicodeDecodeError):
            return None

    def put(self, model, prompt, schema, answer: BaseModel) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(model, prompt, schema)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(answer.model_dump_json(), encoding="utf-8")
        tmp.replace(path)
