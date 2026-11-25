from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
FindingStatus = Literal["confirmed", "needs_review", "rejected"]
CheckStatus = Literal["pass", "fail", "needs_review", "not_applicable", "not_evaluated"]
RequirementType = Literal["functional", "non_functional", "api", "security", "integration", "data",
                          "business_rule", "acceptance_criteria"]
Category = Literal["ambiguity", "incompleteness", "inconsistency", "untestable", "incorrect", "non_atomic",
                   "redundancy", "missing_dependency", "api_design", "security", "financial_logic",
                   "integration", "data_quality", "reliability", "traceability", "design_constraint"]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class Segment(BaseModel):
    """Фрагмент исходного документа; document.text[start:end] == text."""
    id: str
    kind: Literal["heading", "paragraph", "list_item", "table_row", "code"]
    text: str
    section: str
    start: int
    end: int
    source_id: str | None = None
    cells: list[str] = []
    columns: list[str] = []
    page: int | None = None


class Document(BaseModel):
    name: str
    format: Literal["markdown", "pdf"]
    text: str
    segments: list[Segment]


class CriterionCheck(BaseModel):
    criterion: str
    status: CheckStatus
    explanation: str = ""


class Requirement(BaseModel):
    id: str
    source_id: str | None = None
    summary: str
    text: str
    section: str
    source_start: int
    source_end: int
    spans: list[tuple[int, int]] = []
    page: int | None = None
    requirement_type: RequirementType
    type_confidence: float
    segment_ids: list[str]
    checks: list[CriterionCheck] = []


class Evidence(BaseModel):
    requirement_id: str | None
    quote: str
    section: str
    start: int
    end: int
    page: int | None = None


class Fix(BaseModel):
    original_text: str
    proposed_text: str
    rationale: str
    changes: str
    acceptance_criteria: str
    clarification_required: bool
    clarification_question: str = ""


class Finding(BaseModel):
    id: str
    title: str
    category: Category
    criteria: list[str] = []
    severity: Severity
    confidence: float
    requirement_ids: list[str]
    evidence: list[Evidence]
    explanation: str
    impact: str
    recommendation: str
    status: FindingStatus
    source: str = "llm"
    rule_id: str | None = None
    is_gap: bool = False
    stage: str = ""
    validation_note: str = ""
    fix: Fix | None = None


class StageResult(BaseModel):
    id: str
    title: str
    status: Literal["completed", "partial", "failed", "skipped"]
    message: str = ""
    seconds: float = 0
    models: list[str] = []


class Dimension(BaseModel):
    id: str
    title: str
    weight: float
    score: int | None


class Readiness(BaseModel):
    score: int | None
    status: Literal["ready", "ready_with_conditions", "not_ready", "not_evaluated"]
    coverage: int
    dimensions: list[Dimension]


class Summary(BaseModel):
    requirements_count: int
    findings_count: int
    confirmed_count: int
    needs_review_count: int
    rejected_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    requirements_with_violations: int


class Question(BaseModel):
    id: str
    finding_ids: list[str]
    severity: Severity
    requirement_ids: list[str]
    text: str


class Verdict(BaseModel):
    development: str
    testing: str
    text: str
    priorities: list[str]


class AnalysisOptions(BaseModel):
    atomic_analysis: bool = True
    consistency_analysis: bool = True
    fintech_analysis: bool = True
    security_analysis: bool = True
    generate_fixes: bool = True


class AnalysisReport(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    document_name: str
    document_text: str
    analyzed_at: datetime
    duration_seconds: float
    agent_version: str
    model_name: str
    status: Literal["completed", "partial", "failed"]
    stages: list[StageResult]
    requirements: list[Requirement]
    unassigned_segments: list[Segment] = []
    set_checks: list[CriterionCheck]
    findings: list[Finding]
    rejected_findings: list[Finding] = Field(default_factory=list)
    readiness: Readiness
    summary: Summary
    verdict: Verdict
    questions: list[Question] = []
