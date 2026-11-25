from app.errors import LLMError
from app.llm.schemas import (AtomicOut, ConflictsOut, ExtractionOut, FindingsOut, DuplicatesOut, FixesOut, FintechOut, SetOut, ValidationOut)

CRIT = ["necessary", "appropriate", "unambiguous", "complete", "singular", "feasible", "verifiable", "correct", "conforming"]
SET = ["complete", "consistent", "feasible", "comprehensible", "validatable"]


def raw(title="Не задано время отправки", quote="Система быстро отправляет push", conf=.9, **kw):
    d = dict(title=title, category="ambiguity", criterion="unambiguous", severity="medium", confidence=conf,
             evidence=[dict(requirement_id="REQ-002", quote=quote)], explanation="«быстро» не измеримо",
             impact="нельзя проверить", recommendation="задать предел", is_gap=False)
    return {**d, **kw}


class FakeLLM:
    """Модель-заглушка: ответы по схеме ответа; fail — набор этапов, которые падают."""
    model = "fake"

    def __init__(self, findings=None, fail=(), verdict="confirmed"):
        self.findings = findings if findings is not None else [raw()]
        self.fail, self.verdict, self.prompts = set(fail), verdict, []

    async def generate(self, prompt, schema, deadline=None):
        self.prompts.append((schema, prompt))
        if schema.__name__ in self.fail:
            raise LLMError("сбой")
        return getattr(self, schema.__name__)(prompt)

    def ExtractionOut(self, prompt):
        import re
        ids = re.findall(r"^\[(S\d+)\]", prompt, re.M)
        return ExtractionOut(requirements=[dict(segment_ids=[i], summary="кратко " + i, requirement_type="functional", type_confidence=.9) for i in ids])

    def AtomicOut(self, prompt):
        import re
        ids = re.findall(r"^\[(REQ-\d+)\]", prompt, re.M)
        return AtomicOut(requirements=[dict(requirement_id=i, checks=[dict(criterion=c, status="pass", explanation="ок") for c in CRIT]) for i in ids],
                         findings=self.findings if "REQ-002" in ids else [])

    def SetOut(self, prompt):
        return SetOut(checks=[dict(criterion=c, status="pass", explanation="ок") for c in SET], traces=[], findings=[])

    def FindingsOut(self, prompt):
        return FindingsOut(findings=[])

    def ConflictsOut(self, prompt):
        return ConflictsOut(pairs=[], findings=[])

    def FintechOut(self, prompt):
        return FintechOut(scenarios=[], findings=[])

    def DuplicatesOut(self, prompt):
        return DuplicatesOut(groups=[])

    def ValidationOut(self, prompt):
        import re
        return ValidationOut(verdicts=[dict(finding_id=i, counterargument="", answered_elsewhere=False, verdict=self.verdict, severity="medium", reason="проверено", duplicate_of="")
                                       for i in dict.fromkeys(re.findall(r'"id": "([^"]+)"', prompt))])

    def FixesOut(self, prompt):
        import re
        return FixesOut(fixes=[dict(finding_id=i, proposed_text="Новый текст", rationale="почему", changes="что", acceptance_criteria="критерий",
                                    clarification_required=False, clarification_question="") for i in dict.fromkeys(re.findall(r'"id": "([^"]+)"', prompt))])
