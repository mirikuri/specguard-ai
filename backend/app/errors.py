class SpecGuardError(Exception):
    """Базовая ошибка; текст можно показывать пользователю."""


class DocumentError(SpecGuardError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class LLMError(SpecGuardError):
    """Обращение к модели не удалось.

    can_switch — имеет смысл попробовать другую модель; exhausted — эта до конца прогона недоступна;
    provider — недоступен весь провайдер (ключ, суточный лимит): поможет только модель другого провайдера.
    """

    def __init__(self, message: str, can_switch: bool = False, exhausted: bool = False, provider: bool = False):
        super().__init__(message)
        self.can_switch, self.exhausted, self.provider = can_switch, exhausted, provider
