"""Готовые проверки на диске: переживают перезапуск сервера. Файлы доступны только владельцу."""
import json
import logging
import os
import re
from pathlib import Path

from .models import AnalysisReport

log = logging.getLogger("specguard.store")
ID = re.compile(r"analysis_[A-Za-z0-9_-]{12}")


class AnalysisStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, aid: str) -> Path:
        if not ID.fullmatch(aid):
            raise ValueError("Недопустимый номер проверки.")
        return self.directory / f"{aid}.json"

    def save(self, a: dict) -> None:
        path = self._path(a["analysis_id"])
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({**a, "report": a["report"].model_dump(mode="json")}, f, ensure_ascii=False)
        tmp.replace(path)

    def load(self) -> dict[str, dict]:
        items = []
        for path in self.directory.glob("analysis_*.json"):
            try:
                a = json.loads(path.read_text(encoding="utf-8"))
                a["report"] = AnalysisReport.model_validate(a["report"])
                if a["analysis_id"] != path.stem or not ID.fullmatch(path.stem):
                    raise ValueError
                a["created_at"] + ""
                items.append(a)
            except (OSError, ValueError, KeyError, TypeError):
                log.warning("Файл проверки %s не прочитан", path.name)
        items.sort(key=lambda a: a["created_at"])
        return {a["analysis_id"]: a for a in items}

    def delete(self, aid: str) -> None:
        self._path(aid).unlink(missing_ok=True)
