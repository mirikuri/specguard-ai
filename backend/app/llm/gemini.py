import asyncio
import logging
import re

from pydantic import BaseModel, ValidationError

from ..errors import LLMError
from ..prompts_loader import load_prompt
from .router import ModelRouter

log = logging.getLogger("specguard.llm")
TRANSIENT = {408, 429, 500, 502, 503, 504}


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 120, max_retries: int = 2,
                 min_interval: float = 4, backoff: float = 2, models=None):
        self.model, self.timeout, self.max_retries = model, timeout, max_retries
        self.min_interval, self.backoff = min_interval, backoff
        self._models = models
        self._api_key = api_key
        self._lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(2)
        self._next_at = 0.0

    def _get_models(self):
        if self._models is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=self._api_key,
                                        http_options=types.HttpOptions(timeout=int(self.timeout * 1000)))
            self._models = self._client.aio.models
        return self._models

    async def _throttle(self):
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if self._next_at > now:
                await asyncio.sleep(self._next_at - now)
            self._next_at = asyncio.get_running_loop().time() + self.min_interval

    async def generate[T: BaseModel](self, prompt: str, schema: type[T], deadline: float | None = None) -> T:
        loop = asyncio.get_running_loop()
        reason, quota = "", False
        for attempt in range(self.max_retries + 1):
            await self._throttle()
            left = self.timeout if deadline is None else min(self.timeout, deadline - loop.time())
            if left <= 0:
                raise LLMError("Истекло общее время анализа.")
            delay, quota = self.backoff * 2 ** attempt, False
            try:
                async with self._slots, asyncio.timeout(left):
                    response = await self._get_models().generate_content(
                        model=self.model, contents=prompt,
                        config={"system_instruction": load_prompt("system"), "temperature": 0,
                                "response_mime_type": "application/json", "response_schema": schema})
                if response.text:
                    return schema.model_validate_json(response.text)
                reason = "модель вернула пустой ответ"
            except ValidationError:
                reason = "ответ модели не соответствует схеме"
            except TimeoutError:
                reason = "превышено время ожидания модели"
            except Exception as e:  # SDK бросает разные типы; текст ошибки не логируем — в нём может быть ключ
                code = getattr(e, "code", None)
                if code == 429 and re.search(r"per_?day", str(e), re.I):
                    raise LLMError("Исчерпан суточный лимит запросов Gemini (429).", True, True) from None
                if code == 429:
                    quota = True
                    reason = "исчерпан лимит запросов Gemini (429)"
                    if m := re.search(r"retry(?:Delay\W+| in )(\d+(?:\.\d+)?)\s*s", str(e)):
                        delay = min(max(delay, float(m[1])), 65)
                elif code in TRANSIENT:
                    reason = f"временная ошибка Gemini ({code})"
                elif isinstance(code, int):
                    hint = {400: "проверьте ключ и имя модели", 401: "неверный ключ", 403: "ключ не имеет доступа",
                            404: "модель не найдена, проверьте GEMINI_MODEL"}.get(code, "")
                    raise LLMError(f"Gemini отклонил запрос ({code}){': ' + hint if hint else ''}.",
                                   can_switch=code == 404, exhausted=code == 404) from None
                else:
                    reason = f"ошибка соединения с Gemini ({type(e).__name__})"
            log.warning("%s: %s, попытка %d: %s", self.model, schema.__name__, attempt + 1, reason)
            if attempt < self.max_retries:
                if deadline is not None and loop.time() + delay >= deadline:
                    raise LLMError(f"Истекло общее время анализа; последняя причина: {reason}.")
                await asyncio.sleep(delay)
        raise LLMError(f"Не получен ответ модели: {reason}.", can_switch=True, exhausted=quota)


def make_llm(settings, cache=None) -> ModelRouter | None:
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        return None
    main = settings.gemini_model
    light, validator = settings.gemini_light_model or main, settings.gemini_validator_model or main
    names = [main, validator, *settings.gemini_fallback_models.split(","), light]
    clients = {n: GeminiClient(settings.gemini_api_key, n, settings.llm_timeout, settings.max_retries, settings.llm_min_interval)
               for n in dict.fromkeys(x.strip() for x in names) if n}
    return ModelRouter(clients, main, light, validator, cache)
