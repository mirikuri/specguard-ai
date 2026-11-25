SEVERITY = {"critical": "Критичная", "high": "Высокая", "medium": "Средняя", "low": "Низкая", "info": "Справочно"}
FINDING_STATUS = {"confirmed": "Подтверждено", "needs_review": "Требует решения", "rejected": "Отклонено"}
CHECK = {"pass": "да", "fail": "НЕТ", "needs_review": "уточнить", "not_applicable": "н/п", "not_evaluated": "не оценено"}
REPORT_STATUS = {"completed": "Завершён", "partial": "Частичный", "failed": "Ошибка"}
STAGE_STATUS = {"completed": "выполнен", "partial": "выполнен частично", "failed": "не выполнен", "skipped": "пропущен"}
READINESS = {"ready": "Готово", "ready_with_conditions": "Готово с условиями", "not_ready": "Не готово",
             "not_evaluated": "Не оценено"}
SOURCE = {"llm": "модель", "rule": "программное правило", "rule+llm": "правило и модель"}
TYPE = {"functional": "функциональное", "non_functional": "нефункциональное", "api": "API", "security": "безопасность",
        "integration": "интеграция", "data": "данные", "business_rule": "бизнес-правило",
        "acceptance_criteria": "критерий приёмки"}
CATEGORY = {"ambiguity": "Неоднозначность", "incompleteness": "Неполнота", "inconsistency": "Противоречие",
            "untestable": "Непроверяемость", "incorrect": "Некорректность", "non_atomic": "Неатомарность",
            "redundancy": "Дублирование", "missing_dependency": "Нет зависимости", "api_design": "Контракт API",
            "security": "Безопасность", "financial_logic": "Финансовая логика", "integration": "Интеграция",
            "data_quality": "Данные", "reliability": "Надёжность", "traceability": "Прослеживаемость",
            "design_constraint": "Лишнее проектное решение"}
