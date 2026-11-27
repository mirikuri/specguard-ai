import asyncio
import logging
from contextvars import ContextVar
import time

from ..errors import LLMError
from .schemas import foreign_text

log = logging.getLogger("specguard.llm")
ROLE = {"ExtractionOut": "light", "FixesOut": "light", "DuplicatesOut": "light", "ValidationOut": "validator"}  # остальные — main
STAGE_MODELS: ContextVar[list[str] | None] = ContextVar("stage_models", default=None)
EVENTS: ContextVar = ContextVar("events", default=None)  # журнал для пользователя: (вид, текст)
FINDERS = {"ConflictsOut", "AtomicOut", "SetOut", "FintechOut"}


def tell(kind: str, text: str) -> None:
    if (emit := EVENTS.get()) is not None:
        emit(kind, text)


def short(model: str) -> str:
    return model.rsplit("/", 1)[-1].removesuffix(":free")


class ModelRouter:
    """Этапы распределены по моделям; при недоступности одной запрос уходит следующей."""

    def __init__(self, clients: dict, main: str, light: str, validator: str, cache=None, api=None, need: int = 0,
                 apis: list | None = None):
        self.clients, self.cache, self.need = clients, cache, need
        self.apis = apis if apis is not None else [api] if api else []
        self.api = self.apis[0] if self.apis else None
        self.roles = {"main": main, "light": light, "validator": validator}
        self.model = main
        self.used: list[str] = []
        self._finders: set[str] = set()
        self._exhausted: set[str] = set()
        self._busy_until: dict[str, float] = {}
        self.cooldown = 180.0
        self.pause = 20.0

    async def preflight(self) -> None:
        """До начала анализа: ключ принят и лимита хватит на прогон.

        Провайдер, не прошедший проверку, отключается, если есть другой; если не прошёл ни один — ошибка."""
        failed = []
        for api in self.apis:
            try:
                await api.preflight(self.need)
            except LLMError as e:
                failed.append((api, e))
        if failed and len(failed) == len(self.apis):
            raise failed[0][1]
        for api, e in failed:
            names = [n for n, c in self.clients.items() if getattr(c, "api", None) is api]
            self._exhausted.update(names)
            log.warning("провайдер отключён: %s", e)
            tell("warn", f"{e} Проверка продолжится на других моделях.")

    async def close(self) -> None:
        for api in self.apis:
            await api.close()

    @property
    def degraded(self) -> list[str]:
        """Модели, которые искали дефекты вместо основной и проверяющей."""
        return sorted(self._finders - {self.roles["main"], self.roles["validator"]})

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
        chain = self._chain(ROLE.get(schema.__name__, "main"))
        if self.cache:  # сначала ищем готовый ответ любой модели, чтобы не тратить лимит
            for name in chain:
                if (out := self.cache.get(name, prompt, schema)) is not None and foreign_text(out) is None:
                    self._record(name, schema, " (кеш)")
                    return out
        last = LLMError("Лимиты всех настроенных моделей исчерпаны.")
        for name in chain:
            if name in self._exhausted:  # исчерпана параллельным запросом
                continue
            try:
                out = await self.clients[name].generate(prompt, schema, deadline=deadline)
            except LLMError as e:
                if e.provider and (rest := self._drop_provider(name)):
                    log.warning("%s: %s", name, e)
                    tell("warn", f"{e} Запросы переданы модели {short(rest[0])}.")
                    last = LLMError(f"{name}: {e}")
                    continue
                if not e.can_switch:
                    raise
                if e.exhausted:
                    self._exhausted.add(name)
                self._busy_until[name] = time.monotonic() + self.cooldown
                log.warning("%s недоступна для %s: %s", name, schema.__name__, e)
                last = LLMError(f"{name}: {e}", can_switch=True)
                tell("warn", f"Модель {short(name)} не ответила, запрос передан другой")
                continue
            self._record(name, schema)
            if self.cache:
                self.cache.put(name, prompt, schema, out)
            return out
        raise last

    def _drop_provider(self, name) -> list[str]:
        """Отключает все модели провайдера, к которому относится name; возвращает оставшиеся модели."""
        api = getattr(self.clients[name], "api", None)
        self._exhausted.update(n for n, c in self.clients.items() if n == name or (api is not None and getattr(c, "api", None) is api))
        return [n for n in self.clients if n not in self._exhausted]

    def _record(self, name, schema, note=""):
        self.used.append(name + note)
        if (stage := STAGE_MODELS.get()) is not None:
            stage.append(name + note)
        if schema.__name__ in FINDERS:
            self._finders.add(name)
