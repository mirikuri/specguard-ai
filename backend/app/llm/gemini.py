"""Google Gemini API (AI Studio) напрямую, без SDK: запасной или основной провайдер вместо OpenRouter."""
import asyncio
import json
import logging
import re
import time
from collections import deque

import httpx
from pydantic import BaseModel, ValidationError

from ..errors import LLMError
from ..prompts_loader import load_prompt
from .openrouter import RUSSIAN, extract_json, strict_schema
from .schemas import foreign_text

log = logging.getLogger("specguard.llm")
BASE = "https://generativelanguage.googleapis.com/v1beta"
TRANSIENT = {408, 500, 502, 503, 504}
KEY = re.compile(r"api[ _]?key", re.I)
REFUSED = {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}


class Gemini:
    """Соединение с Gemini API, общее для моделей: очередь запросов в минуту и число одновременных."""

    def __init__(self, api_key: str, transport=None, per_minute: int = 10, concurrency: int = 2):
        self._key, self._transport = api_key, transport
        self.per_minute, self.concurrency = per_minute, concurrency
        self._sent: deque[float] = deque()
        self._loop = None
        self.models: list[str] = []  # заполняет make_llm: что проверить до анализа

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._http = httpx.AsyncClient(transport=self._transport, headers={"x-goog-api-key": self._key})
            self._slots, self._turn = asyncio.Semaphore(self.concurrency), asyncio.Lock()

    async def close(self):
        if self._loop is asyncio.get_running_loop():
            await self._http.aclose()
            self._loop = None

    async def preflight(self, need: int = 0) -> None:
        """Ключ принят и первая модель существует. Остаток суточной квоты Gemini API не сообщает."""
        self._bind()
        if not self.models:
            return
        try:
            r = await self._http.get(f"{BASE}/models/{self.models[0]}", timeout=15)
        except httpx.HTTPError:
            return
        if r.status_code in (400, 401, 403):
            raise LLMError("Gemini API не принял ключ: проверьте GEMINI_API_KEY в файле .env.")
        if r.status_code == 404:
            raise LLMError(f"Модель Gemini «{self.models[0]}» не найдена: укажите другую в GEMINI_MODEL.")

    async def _wait_turn(self, deadline):
        async with self._turn:
            while True:
                now = time.monotonic()
                while self._sent and now - self._sent[0] >= 60:
                    self._sent.popleft()
                if len(self._sent) < self.per_minute:
                    self._sent.append(now)
                    return
                wait = 60 - (now - self._sent[0])
                if deadline is not None and asyncio.get_running_loop().time() + wait >= deadline:
                    raise LLMError("Истекло общее время анализа в очереди запросов.")
                await asyncio.sleep(wait)

    async def post(self, model: str, body: dict, idle: float, deadline: float | None) -> tuple[int, dict]:
        """Ответ потоком (SSE): ждём не дольше idle секунд от последнего фрагмента. Возвращает собранный ответ."""
        self._bind()
        loop = asyncio.get_running_loop()
        limit = lambda: loop.time() + idle if deadline is None else min(loop.time() + idle, deadline)
        async with self._slots:
            await self._wait_turn(deadline)
            async with asyncio.timeout_at(limit()) as clock:
                url = f"{BASE}/models/{model}:streamGenerateContent?alt=sse"
                async with self._http.stream("POST", url, json=body, timeout=None) as r:
                    if "text/event-stream" not in r.headers.get("content-type", ""):
                        await r.aread()
                        data = r.json()
                        return r.status_code, data if isinstance(data, dict) else {}
                    text, finish, blocked = [], None, None
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = json.loads(line[5:].strip())
                        if not isinstance(chunk, dict):
                            continue
                        clock.reschedule(limit())
                        if chunk.get("error"):
                            return r.status_code, {"error": chunk["error"]}
                        blocked = (chunk.get("promptFeedback") or {}).get("blockReason") or blocked
                        for cand in chunk.get("candidates") or []:
                            for part in (cand.get("content") or {}).get("parts") or []:
                                if not part.get("thought"):  # рассуждения модели в ответ не входят
                                    text.append(part.get("text") or "")
                            finish = cand.get("finishReason") or finish
                    return r.status_code, {"text": "".join(text), "finish": finish, "blocked": blocked}


class GeminiClient:
    def __init__(self, api: Gemini, model: str, timeout: float = 90, max_retries: int = 1, backoff: float = 2):
        self.api, self.model, self.timeout, self.max_retries, self.backoff = api, model, timeout, max_retries, backoff
        self._plain: set[str] = set()  # схемы, для которых Gemini отверг responseJsonSchema

    def _body(self, prompt: str, schema: type[BaseModel]) -> dict:
        shape = strict_schema(schema)
        config = {"temperature": 0, "responseMimeType": "application/json"}
        if schema.__name__ not in self._plain:
            config["responseJsonSchema"] = shape
        system = load_prompt("system") + "\n\nJSON Schema ответа:\n" + json.dumps(shape, ensure_ascii=False)
        return {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}

    async def generate[T: BaseModel](self, prompt: str, schema: type[T], deadline: float | None = None) -> T:
        loop = asyncio.get_running_loop()
        reason, attempt, ask = "", 0, prompt
        while True:
            if deadline is not None and loop.time() >= deadline:
                raise LLMError("Истекло общее время анализа.")
            delay = self.backoff * 2 ** attempt
            try:
                body = self._body(ask, schema)
                status, data = await self.api.post(self.model, body, self.timeout, deadline)
                err = data.get("error")
                if status != 200 or err:
                    err = err if isinstance(err, dict) else {}
                    code = status if status != 200 else err.get("code")
                    msg = str(err.get("message", ""))
                    if code == 400 and "responseJsonSchema" in body["generationConfig"] and not KEY.search(msg):
                        self._plain.add(schema.__name__)  # схема не подошла: просим JSON только инструкцией
                        continue
                    reason = self._classify(code, msg)
                elif data.get("blocked") or data.get("finish") in REFUSED:
                    raise LLMError("Модель отказалась обрабатывать текст.", can_switch=True, exhausted=True)
                elif data.get("finish") == "MAX_TOKENS":
                    reason = "ответ модели обрезан"
                elif not data.get("text"):
                    reason = "модель вернула пустой ответ"
                else:
                    out = schema.model_validate_json(extract_json(data["text"]))
                    if (bad := foreign_text(out)) is None:
                        return out
                    reason = f"ответ не на русском языке («{bad[:40]}…»)"
                    ask = prompt + RUSSIAN
            except ValidationError:
                reason = "ответ модели не соответствует схеме"
            except TimeoutError:
                if deadline is not None and loop.time() >= deadline:
                    raise LLMError("Истекло общее время анализа.") from None
                reason = f"модель не присылала ответ {self.timeout:g} с"
                attempt = self.max_retries
            except httpx.HTTPError as e:  # текст ошибки не логируем: в нём может быть ключ
                reason = f"ошибка соединения с Gemini API ({type(e).__name__})"
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                reason = "ответ Gemini API не распознан"
            log.warning("%s: %s, попытка %d: %s", self.model, schema.__name__, attempt + 1, reason)
            if attempt >= self.max_retries:
                raise LLMError(f"Не получен ответ модели: {reason}.", can_switch=True)
            if deadline is not None and loop.time() + delay >= deadline:
                raise LLMError(f"Истекло общее время анализа; последняя причина: {reason}.")
            attempt += 1
            await asyncio.sleep(delay)

    @staticmethod
    def _classify(code, msg: str) -> str:
        if code in (401, 403) or (code == 400 and KEY.search(msg)):
            raise LLMError("Gemini API не принял ключ: проверьте GEMINI_API_KEY в файле .env.", provider=True)
        if code == 429:
            if re.search(r"per[-_ ]?day|daily", msg, re.I):  # квоты у моделей отдельные: пробуем следующую
                raise LLMError("Исчерпана суточная квота Gemini для этой модели.", can_switch=True, exhausted=True)
            raise LLMError("Модель Gemini перегружена (429).", can_switch=True)
        if code in TRANSIENT:
            return f"временная ошибка модели ({code})"
        raise LLMError(f"Модель Gemini отклонила запрос ({code})." if code != 404 else "Модель Gemini не найдена (404).",
                       can_switch=True, exhausted=True)
