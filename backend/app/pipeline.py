import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from .analysis.criteria import ATOMIC, SET
from .analysis.dedup import deduplicate, merge, overlaps
from .analysis.evidence import EvidenceLocator
from .analysis.requirements import build_requirements, fallback_requirements
from .analysis.rules import run_rules
from .analysis.scoring import readiness
from .config import agent_version
from .errors import DocumentError, LLMError
from .llm.router import STAGE_MODELS
from .llm.schemas import AtomicOut, ConflictsOut, DuplicatesOut, ExtractionOut, FintechOut, FixesOut, SetOut, ValidationOut
from .models import (SEVERITY_ORDER, AnalysisOptions, AnalysisReport, CriterionCheck, Document, Finding, Fix,
                     Requirement, Segment, StageResult, Summary, Verdict)
from .prompts_loader import build_prompt, wrap_untrusted

log = logging.getLogger("specguard")

STAGES = [
    ("requirements_extraction", "Выделение требований", 5),
    ("structure_rules", "Программные правила", 20),
    ("atomic_analysis", "Проверка каждого требования", 22),
    ("consistency_analysis", "Проверка набора и связей", 45),
    ("fintech_analysis", "Финтех-проверка и пропуски", 60),
    ("evidence_validation", "Проверка доказательств", 72),
    ("fix_generation", "Исправления", 87),
    ("report_generation", "Формирование отчёта", 97),
]
TITLES = {i: t for i, t, _ in STAGES}
PROGRESS = {i: p for i, _, p in STAGES}
ATOMIC_BATCH, VALIDATION_BATCH, FIX_BATCH = 20, 40, 25
CHUNK_CHARS, MAX_CHUNKS = 120_000, 5
CONFIRM_THRESHOLD = 0.75


class Skip(Exception):
    """Этап не нужен или невозможен."""


class Analysis:
    def __init__(self, doc: Document, llm, options: AnalysisOptions, on_progress, timeout: float, on_done=None):
        self.doc, self.llm, self.options, self.on_progress = doc, llm, options, on_progress
        self.deadline = None
        self.on_done = on_done
        self.timeout = timeout
        self.stages: list[StageResult] = []
        self.requirements: list[Requirement] = []
        self.findings: list[Finding] = []
        self.rejected: list[Finding] = []
        self.set_checks: list[CriterionCheck] = []
        self.chunks = self._chunks()
        self.counter = 0

    def _chunks(self) -> list[list[Segment]]:
        chunks, size = [[]], 0
        for s in self.doc.segments:
            if size + len(s.text) > CHUNK_CHARS and chunks[-1]:
                chunks.append([])
                size = 0
            chunks[-1].append(s)
            size += len(s.text)
        if len(chunks) > MAX_CHUNKS or any(sum(len(s.text) for s in c) > CHUNK_CHARS * 2 for c in chunks):
            raise DocumentError(f"Документ слишком большой для анализа: больше {CHUNK_CHARS * MAX_CHUNKS // 1000} тысяч знаков.", 413)
        return chunks

    def chunk_text(self, chunk) -> str:
        return wrap_untrusted(self.doc.text[chunk[0].start:chunk[-1].end])

    async def ask(self, prompt, schema):
        return await self.llm.generate(prompt, schema, deadline=self.deadline)

    async def ask_all(self, calls):
        """Часть пакетов может не выполниться: возвращает ответы и сообщения об ошибках."""
        results = await asyncio.gather(*(self.ask(p, s) for p, s in calls), return_exceptions=True)
        errors = []
        for r in results:
            if isinstance(r, LLMError):
                errors.append(str(r))
            elif isinstance(r, BaseException):
                raise r
        if calls and len(errors) == len(calls):
            raise LLMError(errors[0])
        return results, errors

    async def stage(self, sid, fn, enabled=True, needs_llm=True):
        if self.on_progress:
            self.on_progress(sid, PROGRESS[sid], TITLES[sid])
        started = time.monotonic()
        status, message = "completed", ""
        models: list[str] = []
        STAGE_MODELS.set(models)
        if not enabled:
            status, message = "skipped", "Отключено в параметрах анализа."
        elif needs_llm and self.llm is None:
            status, message = "failed", "Модель не подключена."
        else:
            try:
                note = await fn()
                if note:
                    status, message = "partial", note
            except Skip as e:
                status, message = "skipped", str(e)
            except LLMError as e:
                status, message = "failed", str(e)
                log.warning("Этап %s не выполнен: %s", sid, e)
            except Exception:  # сбой одного этапа не должен терять остальные результаты
                status, message = "failed", "Внутренняя ошибка этапа, подробности в журнале."
                log.exception("Сбой этапа %s", sid)
        self.stages.append(StageResult(id=sid, title=TITLES[sid], status=status, message=message,
                                       seconds=round(time.monotonic() - started, 1),
                                       models=list(dict.fromkeys(models))))
        if self.on_done:
            self.on_done(sid)

    def used_models(self) -> list[str]:
        return getattr(self.llm, "used", [])

    def stage_status(self, sid):
        return next(s.status for s in self.stages if s.id == sid)

    # --- этапы ---

    async def extract(self):
        calls = []
        for chunk in self.chunks:
            lines, section = [], None
            for s in chunk:
                if s.kind == "heading":
                    continue
                if s.section != section:
                    section = s.section
                    lines.append(f"\n(раздел: {section})")
                head = f" (столбцы: {' | '.join(s.columns)})" if s.columns else ""
                sid = f" (номер в документе: {s.source_id})" if s.source_id else ""
                lines.append(f"[{s.id}]{sid}{head} {s.text}")
            calls.append((build_prompt("extraction", segments=wrap_untrusted("\n".join(lines))), ExtractionOut))
        results, errors = await self.ask_all(calls)
        items = [r for x in results if isinstance(x, ExtractionOut) for r in x.requirements]
        self.requirements = build_requirements(self.doc, items)
        if not self.requirements:
            raise LLMError("Модель не выделила ни одного требования.")
        return "; ".join(errors)

    def requirement_list(self, reqs):
        return wrap_untrusted("\n".join(
            f"[{r.id}]{f' (в документе: {r.source_id})' if r.source_id else ''} (раздел: {r.section}) {r.text}" for r in reqs))

    def chunk_requirements(self, chunk):
        ids = {s.id for s in chunk}
        return [r for r in self.requirements if r.segment_ids[0] in ids]

    async def rules(self):
        self.findings += run_rules(self.doc, self.locator)

    def accept(self, raw_findings, stage):
        for f in raw_findings:
            self.counter += 1
            located = [self.locator.locate(e.quote, e.requirement_id) for e in f.evidence]
            evidence, seen = [], set()
            for e in located:
                if e and (e.start, e.end) not in seen:
                    seen.add((e.start, e.end))
                    evidence.append(e)
            finding = Finding(
                id=f"L-{self.counter:03}", title=f.title, category=f.category, criteria=[f.criterion],
                severity=f.severity, confidence=min(max(f.confidence, 0), 1), evidence=evidence,
                requirement_ids=list(dict.fromkeys(e.requirement_id for e in evidence if e.requirement_id)),
                explanation=f.explanation, impact=f.impact, recommendation=f.recommendation, status="needs_review",
                is_gap=f.is_gap, stage=stage, validation_note="Смысловая проверка не выполнена.")
            if f.criterion == "singular" and any(r.id in finding.requirement_ids and len(r.segment_ids) > 1 for r in self.requirements):
                finding.status = "rejected"
                finding.validation_note = "Фрагменты объединил агент, в документе они раздельны."
                self.rejected.append(finding)
            elif not evidence:
                finding.status = "rejected"
                finding.validation_note = "Цитата не найдена в документе."
                self.rejected.append(finding)
            else:
                self.findings.append(finding)

    def accept_traces(self, traces):
        """Расхождение критерия с правилами не теряется, даже если модель не оформила замечание."""
        by_id = {r.id: r for r in self.requirements}
        by_seg = {s.id: s for s in self.doc.segments}
        for t in traces:
            ids = [i for i in dict.fromkeys([t.criterion_requirement_id, *t.rule_requirement_ids]) if i in by_id]
            if t.matches or t.criterion_requirement_id not in by_id or len(ids) < 2:
                continue
            if any(set(ids) <= set(f.requirement_ids) or (t.criterion_requirement_id in f.requirement_ids and f.category == "inconsistency"
                   and set(ids[1:]) & set(f.requirement_ids)) for f in self.findings):
                continue
            self.counter += 1
            evidence = [self.locator.from_segment(by_seg[by_id[i].segment_ids[0]]) for i in ids]
            self.findings.append(Finding(
                id=f"L-{self.counter:03}", title="Критерий приёмки расходится с правилом", category="inconsistency",
                criteria=["consistent"], severity="high", confidence=0.8, evidence=evidence, requirement_ids=ids,
                explanation=f"Расчёт по правилам: {t.calculation} Получается: {t.computed}. Критерий ожидает: {t.expected}.",
                impact="Реализация по правилу не пройдёт приёмку, реализация под критерий нарушит правило.",
                recommendation="Решить, что верно, правило или критерий приёмки, и исправить второе.",
                status="needs_review", stage="consistency_analysis", validation_note="Смысловая проверка не выполнена."))

    async def atomic(self):
        calls = []
        for chunk in self.chunks:
            reqs = self.chunk_requirements(chunk)
            for i in range(0, len(reqs), ATOMIC_BATCH):
                calls.append((build_prompt("atomic", document_context=self.chunk_text(chunk),
                                           requirements=self.requirement_list(reqs[i:i + ATOMIC_BATCH])), AtomicOut))
        results, errors = await self.ask_all(calls)
        by_id = {r.id: r for r in self.requirements}
        for res in results:
            if not isinstance(res, AtomicOut):
                continue
            for item in res.requirements:
                if req := by_id.get(item.requirement_id):
                    given = {c.criterion: c for c in item.checks}
                    req.checks = [CriterionCheck(criterion=c, status=given[c].status, explanation=given[c].explanation)
                                  if c in given else CriterionCheck(criterion=c, status="not_evaluated") for c in ATOMIC]
            self.accept(res.findings, "atomic_analysis")
        missing = [r.id for r in self.requirements
                   if not r.checks or any(c.status == "not_evaluated" for c in r.checks)]
        if missing:
            errors.append("Не полностью проверены: " + ", ".join(missing))
        return "; ".join(errors)

    async def consistency(self):
        calls = []
        for c in self.chunks:
            parts = dict(document=self.chunk_text(c), requirements=self.requirement_list(self.chunk_requirements(c)))
            calls += [(build_prompt("consistency", **parts), SetOut), (build_prompt("conflicts", **parts), ConflictsOut)]
        results, errors = await self.ask_all(calls)
        if not any(isinstance(r, SetOut) for r in results):
            raise LLMError(errors[0])
        rank = {"fail": 0, "needs_review": 1, "pass": 2, "not_applicable": 3}
        best: dict[str, CriterionCheck] = {}
        for res in results:
            if isinstance(res, ConflictsOut):
                self.accept(res.findings, "consistency_analysis")
            if not isinstance(res, SetOut):
                continue
            for c in res.checks:
                if c.criterion not in best or rank[c.status] < rank[best[c.criterion].status]:
                    best[c.criterion] = CriterionCheck(criterion=c.criterion, status=c.status, explanation=c.explanation)
            self.accept(res.findings, "consistency_analysis")
        for res in results:  # после всех замечаний, чтобы не повторить уже найденное
            if isinstance(res, SetOut):
                self.accept_traces(res.traces)
        self.set_checks = [best.get(c, CriterionCheck(criterion=c, status="not_evaluated")) for c in SET]
        if len(self.chunks) > 1:
            errors.append("Большой документ проверен частями: связи между частями не сопоставлены.")
        if any(c not in best for c in SET):
            errors.append("Модель оценила не все критерии набора.")
        return "; ".join(errors)

    async def fintech(self):
        profile = ", ".join([*(["финтех"] if self.options.fintech_analysis else []),
                             *(["безопасность"] if self.options.security_analysis else [])])
        known = wrap_untrusted("\n".join(f"- {f.title}" for f in self.findings if f.rule_id) or "нет")
        results, errors = await self.ask_all([
            (build_prompt("fintech", profile=profile, already_found=known, document=self.chunk_text(c),
                          requirements=self.requirement_list(self.chunk_requirements(c))), FintechOut)
            for c in self.chunks])
        for res in results:
            if isinstance(res, FintechOut):
                self.accept(res.findings, "fintech_analysis")
        return "; ".join(errors)

    async def validate(self):
        # параллельные этапы завершаются в разном порядке: фиксируем порядок и ID замечаний
        self.findings.sort(key=lambda f: (f.rule_id is None, f.stage, f.evidence[0].start, f.title))
        for n, f in enumerate((f for f in self.findings if not f.rule_id), 1):
            f.id = f"L-{n:03}"
        self.findings = deduplicate(self.findings)
        todo = [f for f in self.findings if not f.rule_id]
        if not todo:
            return ""
        if len(self.chunks) == 1:
            context = self.chunk_text(self.chunks[0])
        else:
            sections = {e.section for f in todo for e in f.evidence}
            context = wrap_untrusted("\n\n".join(s.text for s in self.doc.segments if s.section in sections)[:CHUNK_CHARS * 2])
        others = [f for f in self.findings if f.rule_id]
        calls = []
        for i in range(0, len(todo), VALIDATION_BATCH):
            batch = todo[i:i + VALIDATION_BATCH]
            items = [{"id": f.id, "check": not f.rule_id, "title": f.title, "category": f.category, "severity": f.severity,
                      "evidence": [e.quote for e in f.evidence], "requirements": f.requirement_ids,
                      "explanation": f.explanation, "impact": f.impact, "recommendation": f.recommendation}
                     for f in batch + others]
            calls.append((build_prompt("evidence", document=context,
                                       findings=wrap_untrusted(json.dumps(items, ensure_ascii=False, indent=1))), ValidationOut))
        results, errors = await self.ask_all(calls)
        verdicts = {v.finding_id: v for r in results if isinstance(r, ValidationOut) for v in r.verdicts}
        by_id = {f.id: f for f in self.findings}
        kept = list(others)
        for f in todo:
            v = verdicts.get(f.id)
            if v is None:
                errors.append(f"Нет вердикта по замечанию «{f.title}»")
                kept.append(f)
                continue
            severe = f.severity in ("critical", "high")
            f.severity, f.status, f.validation_note = v.severity, v.verdict, v.reason
            if f.status == "rejected" and severe and f.confidence >= 0.9 and len(f.evidence) >= 2:
                f.status = "needs_review"
                f.validation_note = f"Модели разошлись, проверка оспорила замечание: {v.reason}"
            if f.status == "rejected":
                self.rejected.append(f)
                continue
            if f.status == "confirmed":
                if f.confidence < CONFIRM_THRESHOLD:
                    f.status, f.validation_note = "needs_review", f"Уверенность модели ниже порога. {v.reason}"
                elif v.answered_elsewhere:
                    f.status, f.validation_note = "needs_review", f"Ответ, возможно, есть в документе: {v.counterargument}"
                elif f.category == "inconsistency" and len(f.evidence) < 2 and not f.is_gap:
                    f.status, f.validation_note = "needs_review", f"Противоречие подтверждено только одним фрагментом. {v.reason}"
            kept.append(f)
        # Дубли сливаем в последнюю очередь, когда известны все вердикты
        final = []
        for f in kept:
            v = verdicts.get(f.id) if not f.rule_id else None
            target = by_id.get(v.duplicate_of) if v else None
            tv = verdicts.get(target.id) if target else None
            chained = bool(tv and not target.rule_id and tv.duplicate_of in by_id)
            # подтверждённое не прячем внутрь неподтверждённого, если это не явное правило
            downgrade = bool(target) and f.status == "confirmed" and target.status != "confirmed" and not target.rule_id
            if target and target is not f and any(target is k for k in kept) and not chained and not downgrade:
                merge(target, f)
            else:
                final.append(f)
        self.findings = final
        try:
            await self.merge_duplicates()
        except LLMError as e:
            errors.append(f"Поиск дублей не выполнен: {e}")
        return "; ".join(errors)

    async def merge_duplicates(self):
        if len(self.findings) < 2 or all(f.rule_id for f in self.findings):
            return
        items = [{"id": f.id, "title": f.title, "explanation": f.explanation, "recommendation": f.recommendation,
                  "requirements": f.requirement_ids} for f in self.findings]
        out = await self.ask(build_prompt("duplicates", findings=wrap_untrusted(json.dumps(items, ensure_ascii=False, indent=1))), DuplicatesOut)
        by_id = {f.id: f for f in self.findings}
        for group in out.groups:
            found = [by_id[i] for i in dict.fromkeys(group) if i in by_id]
            if len(found) < 2:
                continue
            # главное: правило, затем подтверждённое, затем самое серьёзное
            main, *rest = sorted(found, key=lambda f: (not f.rule_id, f.status != "confirmed", SEVERITY_ORDER[f.severity]))
            for extra in rest:
                shared = overlaps(main, extra) or set(main.requirement_ids) & set(extra.requirement_ids)
                hides = extra.status == "confirmed" and main.status != "confirmed" and not main.rule_id
                if shared and not hides and not (main.rule_id and extra.rule_id):
                    merge(main, extra)
                    del by_id[extra.id]
        self.findings = list(by_id.values())

    async def fixes(self):
        if not self.findings:
            return ""
        by_req = {r.id: r for r in self.requirements}

        def original(f):
            req = by_req.get(f.evidence[0].requirement_id)
            return req.text if req else f.evidence[0].quote

        calls = []
        for i in range(0, len(self.findings), FIX_BATCH):
            items = [{"id": f.id, "title": f.title, "status": f.status, "original_requirement": original(f),
                      "related_requirements": {i: by_req[i].text for i in f.requirement_ids if i in by_req},
                      "evidence": [e.quote for e in f.evidence], "explanation": f.explanation,
                      "recommendation": f.recommendation} for f in self.findings[i:i + FIX_BATCH]]
            calls.append((build_prompt("fixes", findings=wrap_untrusted(json.dumps(items, ensure_ascii=False, indent=1))), FixesOut))
        results, errors = await self.ask_all(calls)
        by_id = {f.id: f for f in self.findings}
        for res in results:
            if isinstance(res, FixesOut):
                for x in res.fixes:
                    if f := by_id.get(x.finding_id):
                        f.fix = Fix(original_text=original(f), **x.model_dump(exclude={"finding_id"}))
        if absent := [f.title for f in self.findings if not f.fix]:
            errors.append(f"Без исправления осталось замечаний: {len(absent)}")
        return "; ".join(errors)

    # --- сборка ---

    def reconcile_checks(self):
        """Статус критерия должен совпадать с замечаниями, прошедшими валидацию."""
        atomic_done = {r.id for r in self.requirements if r.checks}
        for r in self.requirements:
            if r.id not in atomic_done:
                r.checks = [CriterionCheck(criterion=c, status="not_evaluated", explanation="Этап не выполнен.") for c in ATOMIC]
            for c in r.checks:
                own = [f for f in self.findings if r.id in f.requirement_ids and c.criterion in f.criteria]
                confirmed = [f for f in own if f.status == "confirmed"]
                if confirmed:
                    c.status, c.explanation = "fail", "; ".join(f"{f.id}: {f.title}" for f in confirmed)
                elif own:
                    c.status, c.explanation = "needs_review", "; ".join(f"{f.id}: {f.title}" for f in own)
                elif c.status in ("fail", "needs_review"):
                    denied = [f for f in self.rejected if r.id in f.requirement_ids and c.criterion in f.criteria]
                    if denied:
                        c.status, c.explanation = "pass", "Замечание модели отклонено при валидации."
                    else:
                        c.status = "needs_review"
                        c.explanation = f"{c.explanation} (без подтверждённого замечания)".strip()
        if not self.set_checks:
            self.set_checks = [CriterionCheck(criterion=c, status="not_evaluated", explanation="Этап не выполнен.") for c in SET]
        match = {"consistent": ({"inconsistency"}, "consistent"), "complete": ({"incompleteness"}, "complete"),
                 "validatable": ({"untestable"}, "validatable"), "feasible": (set(), None), "comprehensible": (set(), "comprehensible")}
        for c in self.set_checks:
            kinds, criterion = match[c.criterion]
            own = [f for f in self.findings if f.status == "confirmed" and f.severity not in ("low", "info")
                   and (f.category in kinds or criterion in f.criteria)]
            if own:
                c.status, c.explanation = "fail", f"{c.explanation} Подтверждено: {', '.join(f.id for f in own)}.".strip()
            elif c.status == "fail":
                c.status = "needs_review"
                c.explanation += " (без подтверждённого замечания)"

    def finish(self, started: datetime, t0: float) -> AnalysisReport:
        key = lambda f: (f.status != "confirmed", SEVERITY_ORDER[f.severity], f.evidence[0].start if f.evidence else 0)
        self.findings.sort(key=key)
        for n, f in enumerate(self.findings, 1):
            f.id = f"F-{n:03}"
        for n, f in enumerate(self.rejected, 1):
            f.id = f"X-{n:03}"
        self.reconcile_checks()
        self.stages.append(StageResult(id="report_generation", title=TITLES["report_generation"], status="completed"))
        status = "partial" if any(s.status in ("failed", "partial") for s in self.stages) else "completed"

        done = lambda sid: self.stage_status(sid) == "completed"
        available = {"traceability"}
        if done("requirements_extraction") and done("evidence_validation"):
            if done("atomic_analysis"):
                available |= {"unambiguity", "testability"}
            if done("consistency_analysis"):
                available.add("consistency")
            if done("atomic_analysis") and done("consistency_analysis"):
                available.add("completeness")
        ready = readiness(self.requirements, self.findings, available, status)

        if ready.status == "ready" and getattr(self.llm, "degraded", []):
            ready.status = "ready_with_conditions"

        count = lambda **kw: sum(all(getattr(f, k) == v for k, v in kw.items()) for f in self.findings)
        violated = {i for f in self.findings if f.status == "confirmed" for i in f.requirement_ids}
        summary = Summary(
            requirements_count=len(self.requirements), findings_count=len(self.findings),
            confirmed_count=count(status="confirmed"), needs_review_count=count(status="needs_review"),
            rejected_count=len(self.rejected), requirements_with_violations=len(violated),
            **{f"{s}_count": count(severity=s, status="confirmed") for s in SEVERITY_ORDER})
        used = {i for r in self.requirements for i in r.segment_ids}
        return AnalysisReport(
            document_name=self.doc.name, document_text=self.doc.text, analyzed_at=started,
            duration_seconds=round(time.monotonic() - t0, 1), agent_version=agent_version(),
            model_name=(", ".join(dict.fromkeys(self.used_models())) or self.llm.model) if self.llm else "не использовалась", status=status, stages=self.stages,
            requirements=self.requirements,
            unassigned_segments=[s for s in self.doc.segments if s.kind != "heading" and s.id not in used],
            set_checks=self.set_checks, findings=self.findings, rejected_findings=self.rejected,
            readiness=ready, summary=summary, verdict=self.verdict(ready, status))

    def verdict(self, ready, status) -> Verdict:
        confirmed = [f for f in self.findings if f.status == "confirmed"]
        dev = {"ready": "можно", "ready_with_conditions": "можно после устранения условий", "not_ready": "нельзя",
               "not_evaluated": "оценка невозможна: анализ выполнен не полностью"}[ready.status]
        blocking = [f for f in confirmed if f.severity in ("critical", "high")
                    and (f.category in ("untestable", "inconsistency", "incorrect") or {"verifiable", "consistent", "validatable"} & set(f.criteria))]
        test = dev
        if blocking and ready.status in ("ready", "ready_with_conditions"):
            test = "нельзя для затронутых требований: " + ", ".join(sorted({i for f in blocking for i in f.requirement_ids})[:12])
        text = f"Начинать разработку по документу: {dev}. Начинать тестирование: {test}."
        if ready.status == "not_evaluated":
            text = "Вывод о начале разработки и тестирования сделать нельзя: анализ выполнен не полностью."
        if status != "completed":
            bad = [s.title for s in self.stages if s.status in ("failed", "partial")]
            text += " Отчёт частичный. Не выполнено полностью: " + ", ".join(bad) + "."
        if weak := getattr(self.llm, "degraded", []):
            text += (f" Часть поиска выполнили запасные модели ({', '.join(weak)}): они пропускают больше дефектов,"
                     " поэтому оценка может быть завышена. Повторите прогон при доступной основной модели.")
        if any("(кеш)" in m for m in self.used_models()):
            text += " Отладочный прогон: часть ответов модели взята из кеша."
        top = [f for f in confirmed if f.severity in ("critical", "high")] or confirmed
        return Verdict(development=dev, testing=test, text=text,
                       priorities=[f"{f.id} «{f.title}»: {f.recommendation}" for f in top[:7]])

    async def run(self) -> AnalysisReport:
        started, t0 = datetime.now(timezone.utc), time.monotonic()
        self.deadline = asyncio.get_running_loop().time() + self.timeout
        o = self.options
        await self.stage("requirements_extraction", self.extract)
        if not self.requirements:
            self.requirements = fallback_requirements(self.doc)
        self.locator = EvidenceLocator(self.doc, self.requirements)
        await self.stage("structure_rules", self.rules, needs_llm=False)
        await asyncio.gather(
            self.stage("atomic_analysis", self.atomic, o.atomic_analysis),
            self.stage("consistency_analysis", self.consistency, o.consistency_analysis),
            self.stage("fintech_analysis", self.fintech, o.fintech_analysis or o.security_analysis))
        order = list(TITLES)
        self.stages.sort(key=lambda s: order.index(s.id))
        await self.stage("evidence_validation", self.validate)
        await self.stage("fix_generation", self.fixes, o.generate_fixes)
        if self.on_progress:
            self.on_progress("report_generation", PROGRESS["report_generation"], TITLES["report_generation"])
        return self.finish(started, t0)


async def analyze(doc: Document, llm, options: AnalysisOptions | None = None, on_progress=None,
                  timeout: float = 900, on_done=None) -> AnalysisReport:
    return await Analysis(doc, llm, options or AnalysisOptions(), on_progress, timeout, on_done).run()
