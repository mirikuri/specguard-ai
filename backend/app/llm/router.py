import asyncio
import logging
from contextvars import ContextVar
import time

from ..errors import LLMError

log = logging.getLogger("specguard.llm")
ROLE = {"ExtractionOut": "light", "FixesOut": "light", "DuplicatesOut": "light", "ValidationOut": "validator"}  # остальные — main
STAGE_MODELS: ContextVar[list[str] | None] = ContextVar("stage_models", default=None)
FINDERS = {"ConflictsOut", "AtomicOut", "SetOut", "FintechOut"}


class ModelRouter:
    """Этапы распределены по моделям; при недоступности одной запрос уходит следующей."""

    def __init__(self, clients: dict, main: str, light: str, validator: str):
        self.clients = clients
        self.roles = {"main": main, "light": light, "validator": validator}
        self.model = main
        self.used: list[str] = []
        self._finders: set[str] = set()
        self._exhausted: set[str] = set()
        self._busy_until: dict[str, float] = {}
        self.cooldown = 180.0
        self.pause = 20.0

    def _chain(self, role: str) -> list[str]:
        first = self.roles[role]
        chain = [first, *(m for m in self.clients if m != first)]
        if role == "validator":  # проверяет не та модель, что нашла; сортировка устойчива
            chain.sort(key=lambda m: m in self._finders)
        now = time.monotonic()
        chain.sort(key=lambda m: self._busy_until.get(m, 0) > now)  # перегруженные — в конец
        return [m for m in chain if m not in self._exhausted]

    async def generate(self, prompt, schema, deadline=None):
        try:
            return await self._sweep(prompt, schema, deadline)
        except LLMError as e:  # все перегружены: одна пауза и второй круг
            late = deadline is not None and asyncio.get_running_loop().time() + self.pause >= deadline
            if not e.can_switch or late:
                raise
            await asyncio.sleep(self.pause)
            return await self._sweep(prompt, schema, deadline)

    async def _sweep(self, prompt, schema, deadline):
        last = LLMError("Лимиты всех настроенных моделей исчерпаны.")
        for name in self._chain(ROLE.get(schema.__name__, "main")):
            if name in self._exhausted:  # исчерпана параллельным запросом
                continue
            try:
                out = await self.clients[name].generate(prompt, schema, deadline=deadline)
            except LLMError as e:
                if not e.can_switch:
                    raise
                if e.exhausted:
                    self._exhausted.add(name)
                self._busy_until[name] = time.monotonic() + self.cooldown
                log.warning("%s недоступна для %s: %s", name, schema.__name__, e)
                last = LLMError(f"{name}: {e}", can_switch=True)
                continue
            self.used.append(name)
            if (stage := STAGE_MODELS.get()) is not None:
                stage.append(name)
            if schema.__name__ in FINDERS:
                self._finders.add(name)
            return out
        raise last
