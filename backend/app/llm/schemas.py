"""Схемы ответов модели. Без значений по умолчанию: так их принимает structured output."""
import re
from typing import Literal

from pydantic import BaseModel

from ..models import Category, RequirementType, Severity

AtomicCriterion = Literal["necessary", "appropriate", "unambiguous", "complete", "singular", "feasible",
                          "verifiable", "correct", "conforming"]
SetCriterion = Literal["complete", "consistent", "feasible", "comprehensible", "validatable"]
AnyCriterion = Literal["necessary", "appropriate", "unambiguous", "complete", "singular", "feasible", "verifiable",
                       "correct", "conforming", "consistent", "comprehensible", "validatable"]
Status = Literal["pass", "fail", "needs_review", "not_applicable"]


class ExtractedRequirement(BaseModel):
    segment_ids: list[str]
    summary: str
    requirement_type: RequirementType
    type_confidence: float


class ExtractionOut(BaseModel):
    requirements: list[ExtractedRequirement]


class RawEvidence(BaseModel):
    requirement_id: str
    quote: str


class RawFinding(BaseModel):
    title: str
    category: Category
    criterion: AnyCriterion
    severity: Severity
    confidence: float
    evidence: list[RawEvidence]
    explanation: str
    impact: str
    recommendation: str
    is_gap: bool


class AtomicCheck(BaseModel):
    criterion: AtomicCriterion
    status: Status
    explanation: str


class AtomicRequirement(BaseModel):
    requirement_id: str
    checks: list[AtomicCheck]


class AtomicOut(BaseModel):
    requirements: list[AtomicRequirement]
    findings: list[RawFinding]


class RulePair(BaseModel):
    first: str
    second: str
    scenario: str
    by_first: str
    by_second: str
    compatible: bool


class ConflictsOut(BaseModel):
    pairs: list[RulePair]
    findings: list[RawFinding]


class SetCheck(BaseModel):
    criterion: SetCriterion
    status: Status
    explanation: str


class AcceptanceTrace(BaseModel):
    """Порядок полей важен: расчёт идёт раньше вывода."""
    criterion_requirement_id: str
    rule_requirement_ids: list[str]
    calculation: str
    computed: str
    expected: str
    matches: bool


class SetOut(BaseModel):
    traces: list[AcceptanceTrace]
    checks: list[SetCheck]
    findings: list[RawFinding]


class FindingsOut(BaseModel):
    findings: list[RawFinding]


class Scenario(BaseModel):
    scenario: str
    applicable: bool
    covered_by: list[str]
    unanswered: str


class FintechOut(BaseModel):
    scenarios: list[Scenario]
    findings: list[RawFinding]


class DuplicatesOut(BaseModel):
    groups: list[list[str]]


class Verdict(BaseModel):
    finding_id: str
    counterargument: str
    answered_elsewhere: bool
    verdict: Literal["confirmed", "needs_review", "rejected"]
    severity: Severity
    reason: str
    duplicate_of: str


class ValidationOut(BaseModel):
    verdicts: list[Verdict]


class RawFix(BaseModel):
    finding_id: str
    proposed_text: str
    rationale: str
    changes: str
    acceptance_criteria: str
    clarification_required: bool
    clarification_question: str


class FixesOut(BaseModel):
    fixes: list[RawFix]


# Поля, которые модель пишет своими словами и которые попадают в отчёт. Цитаты, ID и предложенный текст
# требования сюда не входят: они могут законно состоять из латиницы (поля API, URL).
PROSE = {"summary", "title", "explanation", "impact", "recommendation", "scenario", "by_first", "by_second",
         "unanswered", "counterargument", "reason", "rationale", "changes", "acceptance_criteria",
         "clarification_question"}
_LAT, _CYR = re.compile(r"[A-Za-z]"), re.compile(r"[А-Яа-яЁё]")


def foreign_text(out: BaseModel) -> str | None:
    """Первое прозаическое поле, где латиница преобладает: модель ответила не по-русски.

    Короткие строки не проверяем: «GET /saveLimit» или «HTTP 404» — нормальный текст замечания."""
    def walk(x, key=None):
        if isinstance(x, BaseModel):
            for k in type(x).model_fields:
                if (hit := walk(getattr(x, k), k)) is not None:
                    return hit
        elif isinstance(x, list):
            for v in x:
                if (hit := walk(v, key)) is not None:
                    return hit
        elif isinstance(x, str) and key in PROSE:
            lat, cyr = len(_LAT.findall(x)), len(_CYR.findall(x))
            if lat >= 20 and lat > cyr:
                return x
        return None
    return walk(out)
