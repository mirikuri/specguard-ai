import html
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .. import labels as L
from ..analysis.criteria import ATOMIC, CRITERIA, SET
from ..models import AnalysisReport

MEDIA = {"html": "text/html", "json": "application/json", "md": "text/markdown"}
CRITICAL_KINDS = {"untestable": "Непроверяемые", "inconsistency": "Противоречивые", "incompleteness": "Неполные"}
CRITERION_KIND = {"verifiable": "untestable", "validatable": "untestable", "consistent": "inconsistency",
                  "complete": "incompleteness"}
env = Environment(loader=FileSystemLoader(Path(__file__).parent), autoescape=True, trim_blocks=True, lstrip_blocks=True)


def line_of(report: AnalysisReport, pos: int) -> int:
    return report.document_text.count("\n", 0, pos) + 1


def critical_defects(report: AnalysisReport) -> dict[str, list]:
    """Непроверяемые, противоречивые и неполные формулировки (п. 6 условий). Серьёзные открытые вопросы тоже здесь."""
    groups = {t: [] for t in CRITICAL_KINDS.values()}
    for f in report.findings:
        if f.severity not in ("critical", "high", "medium") or f.status != "confirmed" and f.severity == "medium":
            continue
        kinds = {f.category} | {CRITERION_KIND.get(c) for c in f.criteria}
        for k, title in CRITICAL_KINDS.items():
            if k in kinds:
                groups[title].append(f)
    return groups


def render(report: AnalysisReport, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if fmt == "md":
        return to_markdown(report)
    if fmt == "html":
        return env.get_template("report.html").render(
            r=report, L=L, ATOMIC=ATOMIC, SET=SET, CRITERIA=CRITERIA, critical=critical_defects(report),
            line=lambda p: line_of(report, p))
    raise ValueError(fmt)


def no_links(text: str) -> str:
    """Ссылки и картинки из документа не должны загружаться при просмотре отчёта."""
    return text.replace("](", "]\\(")


def esc(text: str) -> str:
    return no_links(html.escape(" ".join(str(text).split()), quote=False)).replace("|", "\\|")


def quote(text: str) -> str:
    return "\n".join("> " + no_links(html.escape(line, quote=False)) for line in text.splitlines())


def to_markdown(r: AnalysisReport) -> str:
    o: list[str] = []
    w = o.append

    def table(head, rows):
        w("| " + " | ".join(head) + " |")
        w("|" + " --- |" * len(head))
        for row in rows:
            w("| " + " | ".join(esc(c) for c in row) + " |")
        w("")

    w(f"# Отчёт о проверке требований: {esc(r.document_name)}\n")
    if r.status != "completed":
        w("> **ВНИМАНИЕ: отчёт частичный.** Не все этапы выполнены, отсутствие замечаний не означает отсутствие дефектов.\n")
    w("## 1. Паспорт прогона\n")
    table(["Поле", "Значение"], [
        ("Документ", r.document_name), ("Дата", r.analyzed_at.strftime("%d.%m.%Y %H:%M:%S UTC")), ("Модель", r.model_name),
        ("Версия агента", r.agent_version), ("Статус", L.REPORT_STATUS[r.status]), ("Длительность", f"{r.duration_seconds} с"),
        ("Критерии", "ISO/IEC/IEEE 29148:2018, п. 5.2.5 и 5.2.6; IEEE Std 830-1998, п. 4.3")])
    table(["Этап", "Статус", "Модель", "Комментарий"], [(s.title, L.STAGE_STATUS[s.status], ", ".join(s.models) or "без модели", s.message) for s in r.stages])

    if r.questions:
        w("## Вопросы аналитику\n")
        w("Сначала самые серьёзные. Обоснование и цитаты — в указанном замечании.\n")
        table(["№", "Серьёзность", "Вопрос", "Требования", "Замечание"], [
            (q.id, L.SEVERITY[q.severity], q.text, ", ".join(q.requirement_ids) or "вне требований", ", ".join(q.finding_ids)) for q in r.questions])

    w("## 2. Как агент нарезал требования\n")
    table(["ID в отчёте", "ID в документе", "Краткая формулировка", "Тип (уверенность)"],
          [(x.id, x.source_id or "нет, присвоен агентом", x.summary, f"{L.TYPE[x.requirement_type]} ({x.type_confidence:.0%})")
           for x in r.requirements])
    if r.unassigned_segments:
        w(f"Не отнесено к требованиям фрагментов: {len(r.unassigned_segments)} (служебные поля, шаблон, пояснения).\n")

    w("## 3. Проверка каждого требования\n")
    for x in r.requirements:
        w(f"### {x.id}{f' ({esc(x.source_id)})' if x.source_id else ''}\n")
        w(f"Раздел: {esc(x.section)}. Строка {line_of(r, x.source_start)}{f', страница {x.page}' if x.page else ''}.\n")
        w(quote(x.text) + "\n")
        table(["Критерий", "Выполнен", "Пояснение"],
              [(ATOMIC.get(c.criterion, c.criterion), L.CHECK[c.status], c.explanation) for c in x.checks])

    w("## 4. Проверка всего набора\n")
    table(["Критерий", "Выполнен", "Пояснение"], [(SET.get(c.criterion, c.criterion), L.CHECK[c.status], c.explanation) for c in r.set_checks])

    w("## 5. Замечания\n")
    if not r.findings:
        w("Подтверждённых замечаний и вопросов нет.\n")
    for f in r.findings:
        w(f"### {f.id}. {esc(f.title)}\n")
        table(["Статус", "Серьёзность", "Уверенность", "Категория", "Критерии", "Требования", "Источник"], [(
            L.FINDING_STATUS[f.status], L.SEVERITY[f.severity], f"{f.confidence:.0%}", L.CATEGORY[f.category],
            ", ".join(CRITERIA.get(c, c) for c in f.criteria), ", ".join(f.requirement_ids) or "фрагмент вне требований", L.SOURCE[f.source])])
        for e in f.evidence:
            w(f"{e.requirement_id or 'Фрагмент'}, строка {line_of(r, e.start)}{f', страница {e.page}' if e.page else ''}, {esc(e.section)}:\n")
            w(quote(e.quote) + "\n")
        w(f"**Почему это проблема.** {esc(f.explanation)}\n")
        w(f"**Последствия.** {esc(f.impact)}\n")
        w(f"**Рекомендация.** {esc(f.recommendation)}\n")
        if f.validation_note:
            w(f"**Проверка замечания.** {esc(f.validation_note)}\n")
        if f.fix:
            w(f"**Вариант исправления.** {esc(f.fix.proposed_text)}\n")
            w(f"**Что изменилось.** {esc(f.fix.changes)} {esc(f.fix.rationale)}\n")
            w(f"**Критерий приёмки.** {esc(f.fix.acceptance_criteria)}\n")
            if f.fix.clarification_required:
                w(f"**Вопрос аналитику.** {esc(f.fix.clarification_question)}\n")

    s = r.summary
    w("## 6. Сводка\n")
    table(["Показатель", "Значение"], [
        ("Требований", s.requirements_count), ("Требований с подтверждёнными нарушениями", s.requirements_with_violations),
        ("Подтверждённых нарушений", s.confirmed_count), ("Замечаний, требующих решения", s.needs_review_count), ("Вопросов аналитику", len(r.questions)),
        ("Отклонено при валидации", s.rejected_count),
        ("Подтверждённых по серьёзности: критичных / высоких / средних / низких", f"{s.critical_count} / {s.high_count} / {s.medium_count} / {s.low_count}"),
        ("Readiness Score", "не рассчитан" if r.readiness.score is None else f"{r.readiness.score} из 100 ({L.READINESS[r.readiness.status]})"),
        ("Покрытие оценки", f"{r.readiness.coverage}%")])
    table(["Измерение", "Вес", "Оценка"], [(d.title, f"{d.weight:.0%}", "не оценено" if d.score is None else d.score) for d in r.readiness.dimensions])
    w("Веса и штрафы — собственная методика SpecGuard, не формула ISO.\n")
    w("Критичные дефекты формулировок:\n")
    for title, items in critical_defects(r).items():
        w(f"* **{title}:** " + ("; ".join(f"{f.id} ({', '.join(f.requirement_ids) or 'вне требований'}) {esc(f.title)}{' (требует решения)' if f.status == 'needs_review' else ''}" for f in items) or "не обнаружены"))
    w("")
    w("## 7. Итог\n")
    w(esc(r.verdict.text) + "\n")
    if r.verdict.priorities:
        w("Исправить в первую очередь:\n")
        for i, p in enumerate(r.verdict.priorities, 1):
            w(f"{i}. {esc(p)}")
    return "\n".join(o) + "\n"
