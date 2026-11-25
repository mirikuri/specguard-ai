import type { Severity } from './types'

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
export const SEVERITY: Record<string, string> = { critical: 'Критичная', high: 'Высокая', medium: 'Средняя', low: 'Низкая', info: 'Справочно' }
export const STATUS: Record<string, string> = { confirmed: 'Подтверждено', needs_review: 'Требует решения', rejected: 'Отклонено' }
export const CHECK: Record<string, string> = { pass: 'Да', fail: 'Нет', needs_review: 'Уточнить', not_applicable: 'Не применимо', not_evaluated: 'Не оценено' }
export const READINESS: Record<string, string> = { ready: 'Готово к разработке', ready_with_conditions: 'Готово с условиями', not_ready: 'Не готово к разработке', not_evaluated: 'Готовность не оценена' }
export const SOURCE: Record<string, string> = { llm: 'модель', rule: 'программное правило', 'rule+llm': 'правило и модель' }
export const STAGE: Record<string, string> = { completed: 'Выполнен', partial: 'Выполнен частично', failed: 'Не выполнен', skipped: 'Пропущен' }
export const TYPE: Record<string, string> = { functional: 'Функциональное', non_functional: 'Нефункциональное', api: 'API', security: 'Безопасность', integration: 'Интеграция', data: 'Данные', business_rule: 'Бизнес-правило', acceptance_criteria: 'Критерий приёмки' }
export const CATEGORY: Record<string, string> = { ambiguity: 'Неоднозначность', incompleteness: 'Неполнота', inconsistency: 'Противоречие', untestable: 'Непроверяемость', incorrect: 'Некорректность', non_atomic: 'Неатомарность', redundancy: 'Дублирование', missing_dependency: 'Нет зависимости', api_design: 'Контракт API', security: 'Безопасность', financial_logic: 'Финансовая логика', integration: 'Интеграция', data_quality: 'Данные', reliability: 'Надёжность', traceability: 'Прослеживаемость', design_constraint: 'Лишнее проектное решение' }
export const CRITERION: Record<string, string> = { necessary: 'Необходимость', appropriate: 'Уместность', unambiguous: 'Однозначность', complete: 'Полнота', singular: 'Атомарность', feasible: 'Реализуемость', verifiable: 'Проверяемость', correct: 'Корректность', conforming: 'Соответствие шаблону', consistent: 'Согласованность', comprehensible: 'Понятность', validatable: 'Возможность валидации' }
export const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)
export function plural(n: number, one: string, few: string, many: string) {
  const a = n % 10, b = n % 100
  return `${n} ${a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many}`
}
/** Цитата для чтения: без служебных знаков Markdown. Точный текст остаётся в документе и выгрузках. */
export const clean = (s: string) => s.replace(/\*\*|`/g, '').replace(/^\s*[|*\-]\s+|\s*\|\s*$/g, '').replace(/\s*\|\s*/g, ' · ').trim()
