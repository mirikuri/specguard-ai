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
from .router import ModelRouter
from .schemas import foreign_text

RUSSIAN = ("\n\nПредыдущий ответ содержал текст не на русском языке. Все поля, кроме цитат и идентификаторов, "
           "пиши только по-русски.")

log = logging.getLogger("specguard.llm")
BASE = "https://openrouter.ai/api/v1"
RUN_REQUESTS = 12  # столько запросов уходит на небольшой документ
NO_REASONING = {"ExtractionOut", "AtomicOut", "FixesOut", "DuplicatesOut"}  # механические шаги: рассуждения замедляют их в 4 раза
TRANSIENT = {408, 429, 500, 502, 503, 504, 524, 529}
ACCOUNT = {401: "неверный ключ, проверьте OPENROUTER_API_KEY", 402: "на счёте нет средств для этой модели",
           403: "у ключа нет доступа"}


def strict_schema(schema: type[BaseModel]) -> dict:
    def close(x):
        if isinstance(x, dict):
            if x.get("type") == "object" and "properties" in x:
                x["additionalProperties"] = False
                x["required"] = list(x["properties"])
            for v in x.values():
                close(v)
        elif isinstance(x, list):
            for v in x:
                close(v)
        return x
    return close(schema.model_json_schema())


def extract_json(text: str) -> str:
    """Модели без строгого JSON добавляют рассуждения и обёртку ```json."""
    text = re.sub(r"^\s*<think>.*?</think>", "", text, flags=re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


class OpenRouter:
    """Соединение, общее для всех моделей: лимит 20 запросов в минуту считается на аккаунт."""

    def __init__(self, api_key: str, transport=None, per_minute: int = 20, concurrency: int = 4):
        self._key, self._transport = api_key, transport
        self.per_minute, self.concurrency = per_minute, concurrency
        self._sent: deque[float] = deque()
        self._loop = None
        self._params: dict[str, list[str]] | None = None

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop:  # примитивы asyncio и соединения принадлежат одному циклу
            self._loop = loop
            self._http = httpx.AsyncClient(transport=self._transport, headers={"Authorization": f"Bearer {self._key}"})
            self._slots, self._turn, self._catalog = asyncio.Semaphore(self.concurrency), asyncio.Lock(), asyncio.Lock()

    async def close(self):
        if self._loop is asyncio.get_running_loop():
            await self._http.aclose()
            self._loop = None

    async def preflight(self, need: int) -> None:
        self._bind()
        try:
            r = await self._http.get(BASE + "/key", timeout=15)
            body = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            return
        if r.status_code in (401, 403):
            raise LLMError("OpenRouter не принял ключ: проверьте OPENROUTER_API_KEY в файле .env.")
        data = body.get("data") if isinstance(body, dict) else None
        free = data.get("free_model_daily_requests") if isinstance(data, dict) else None
        left = free.get("remaining") if isinstance(free, dict) else None
        if isinstance(left, (int, float)) and left < need:
            raise LLMError(f"На сегодня осталось {int(left)} бесплатных запросов OpenRouter, для проверки нужно около {need}. "
                           "Лимит обновляется в 00:00 UTC.")

    async def supports(self, model: str) -> list[str]:
        self._bind()
        async with self._catalog:
            if self._params is None:
                try:
                    r = await self._http.get(BASE + "/models", timeout=20)
                    self._params = {m["id"]: m.get("supported_parameters") or [] for m in r.json()["data"]}
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    self._params = {}  # без справочника просим JSON только текстом
        return self._params.get(model, [])

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

    async def post(self, body: dict, idle: float, deadline: float | None) -> tuple[int, object]:
        """Ответ потоком: ждём не дольше idle секунд от последнего полученного фрагмента, а не весь ответ целиком.

        Медленная, но работающая модель доживает до конца ответа; зависшая обрывается. Комментарии-заглушки
        OpenRouter («processing») прогрессом не считаются. Ошибку до начала потока OpenRouter присылает обычным JSON."""
        self._bind()
        loop = asyncio.get_running_loop()
        limit = lambda: loop.time() + idle if deadline is None else min(loop.time() + idle, deadline)
        async with self._slots:
            await self._wait_turn(deadline)
            async with asyncio.timeout_at(limit()) as clock:
                async with self._http.stream("POST", BASE + "/chat/completions", json={**body, "stream": True},
                                             timeout=None) as r:
                    if "text/event-stream" not in r.headers.get("content-type", ""):
                        await r.aread()
                        return r.status_code, r.json()
                    text, finish = [], None
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        chunk = json.loads(payload)
                        if not isinstance(chunk, dict):
                            continue
                        clock.reschedule(limit())
                        if chunk.get("error"):
                            return r.status_code, {"error": chunk["error"]}
                        for choice in chunk.get("choices") or []:
                            text.append((choice.get("delta") or {}).get("content") or "")
                            finish = choice.get("finish_reason") or finish
                    return r.status_code, {"choices": [{"message": {"content": "".join(text) or None},
                                                        "finish_reason": finish}]}


class OpenRouterClient:
    def __init__(self, api: OpenRouter, model: str, timeout: float = 90, max_retries: int = 1, backoff: float = 2):
        self.api, self.model, self.timeout, self.max_retries, self.backoff = api, model, timeout, max_retries, backoff
        self._plain: set[str] = set()  # схемы, которые поставщик отклонил

    async def _body(self, prompt, schema) -> dict:
        shape = strict_schema(schema)
        body = {"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": load_prompt("system") + "\n\nJSON Schema ответа:\n" + json.dumps(shape, ensure_ascii=False)},
            {"role": "user", "content": prompt}]}
        params = await self.api.supports(self.model)
        if schema.__name__ not in self._plain:
            if schema.__name__ in NO_REASONING and "reasoning" in params:
                body["reasoning"] = {"enabled": False}
            if "structured_outputs" in params:
                body["response_format"] = {"type": "json_schema",
                                           "json_schema": {"name": schema.__name__, "strict": True, "schema": shape}}
            elif "response_format" in params:
                body["response_format"] = {"type": "json_object"}
        return body

    async def generate[T: BaseModel](self, prompt: str, schema: type[T], deadline: float | None = None) -> T:
        loop = asyncio.get_running_loop()
        reason, attempt, ask = "", 0, prompt
        while True:
            if deadline is not None and loop.time() >= deadline:
                raise LLMError("Истекло общее время анализа.")
            delay = self.backoff * 2 ** attempt
            try:
                body = await self._body(ask, schema)
                status, data = await self.api.post(body, self.timeout, deadline)
                data = data if isinstance(data, dict) else {}
                err = data.get("error")
                if status != 200 or err:
                    err = err if isinstance(err, dict) else {}
                    code = status if status != 200 else err.get("code")
                    if code == 400 and ("response_format" in body or "reasoning" in body):
                        self._plain.add(schema.__name__)
                        continue
                    reason = self._classify(code, err)
                else:
                    choice = data["choices"][0]
                    text = choice["message"].get("content")
                    if choice.get("finish_reason") == "length":
                        reason = "ответ модели обрезан"
                    elif choice.get("finish_reason") == "error":
                        reason = "поставщик прервал ответ"
                    elif not text:
                        reason = "модель вернула пустой ответ"
                    else:
                        out = schema.model_validate_json(extract_json(text))
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
                attempt = self.max_retries  # ждать ещё столько же нет смысла, пробуем другую модель
            except httpx.HTTPError as e:  # текст ошибки не логируем: в нём может быть ключ
                reason = f"ошибка соединения с OpenRouter ({type(e).__name__})"
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                reason = "ответ OpenRouter не распознан"
            log.warning("%s: %s, попытка %d: %s", self.model, schema.__name__, attempt + 1, reason)
            if attempt >= self.max_retries:
                raise LLMError(f"Не получен ответ модели: {reason}.", can_switch=True)
            if deadline is not None and loop.time() + delay >= deadline:
                raise LLMError(f"Истекло общее время анализа; последняя причина: {reason}.")
            attempt += 1
            await asyncio.sleep(delay)

    @staticmethod
    def _classify(code, err) -> str:
        meta = err.get("metadata") if isinstance(err.get("metadata"), dict) else {}
        if code == 403 and meta.get("reasons"):
            raise LLMError("Модель отказалась обрабатывать текст.", can_switch=True, exhausted=True)
        if code in ACCOUNT:
            raise LLMError(f"OpenRouter отклонил запрос ({code}): {ACCOUNT[code]}.")
        if code == 429:
            if re.search(r"per[-_ ]day|daily", str(err.get("message", "")), re.I):
                raise LLMError("Исчерпан суточный лимит бесплатных запросов OpenRouter, он обновляется в 00:00 UTC.")
            raise LLMError("Модель перегружена (429).", can_switch=True)
        if code in TRANSIENT:
            return f"временная ошибка модели ({code})"
        raise LLMError(f"Модель отклонила запрос ({code})." if code != 404 else "Модель не найдена или сейчас недоступна (404).",
                       can_switch=True, exhausted=True)


def make_llm(settings, cache=None) -> ModelRouter | None:
    if not settings.openrouter_api_key:
        return None
    main = settings.llm_model
    light, validator = settings.llm_light_model or main, settings.llm_validator_model or main
    names = list(dict.fromkeys(x.strip() for x in [main, validator, *settings.llm_fallback_models.split(","), light] if x.strip()))
    api = OpenRouter(settings.openrouter_api_key)
    clients = {n: OpenRouterClient(api, n, settings.llm_timeout, settings.max_retries) for n in names}
    need = RUN_REQUESTS if any(n.endswith(":free") for n in (main, light, validator)) and not cache else 0
    return ModelRouter(clients, main, light, validator, cache, api=api, need=need)
