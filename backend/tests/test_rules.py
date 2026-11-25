from app.analysis.requirements import fallback_requirements
from app.analysis.evidence import EvidenceLocator
from app.analysis.rules import run_rules
from app.parser import parse_document


def rules(text):
    d = parse_document("a.md", text.encode())
    r = fallback_requirements(d)
    return {f.rule_id: f for f in run_rules(d, EvidenceLocator(d, r))}


API = "# API\n\n| Поле | Значение |\n|---|---|\n| Description | {d} |\n| REST type | {m} |\n| Request URL | {u} |\n"


def test_get_that_saves():
    f = rules(API.format(d="Сохранение порога", m="GET", u="/alerts/saveLimit"))["get-mutates"]
    assert f.severity == "high" and f.status == "confirmed" and len(f.evidence) >= 2


def test_get_that_reads_is_fine():
    assert "get-mutates" not in rules(API.format(d="Чтение настроек", m="GET", u="/alerts/limit"))
    assert "get-mutates" not in rules(API.format(d="Чтение сохранённых настроек", m="GET", u="/alerts/limit"))


def test_post_that_saves_is_fine():
    assert "get-mutates" not in rules(API.format(d="Сохранение порога", m="POST", u="/alerts/limit"))


def test_methods_in_different_sections_do_not_mix():
    text = API.format(d="Чтение", m="GET", u="/limit") + "\n" + API.replace("# API", "# API2").format(d="Сохранение", m="POST", u="/saveLimit")
    assert "get-mutates" not in rules(text)


P = "# A\n\n## Запрос\n\n| Parameter | Format |\n|---|---|\n| `amount` | integer |\n\n## Ответ\n\n| Parameter | Format |\n|---|---|\n| `amount` | {} |\n"


def test_type_mismatch():
    f = rules(P.format("string"))["type-mismatch"]
    assert len(f.evidence) == 2 and "amount" in f.title
    assert "type-mismatch" not in rules(P.format("integer"))


def test_content_type_without_body():
    assert "content-type-no-body" in rules("# A\n\n* Content-Type: `application/json`.\n* Тело не используется.\n")
    assert "content-type-no-body" not in rules("# A\n\n* Content-Type: `application/json`.\n")


def test_undocumented_success_code():
    t = "# A\n\nЕсли результат 200 или 201 — успешный.\n\n**200.** Успех.\n"
    f = rules(t)["undocumented-status"]
    assert "201" in f.title
    assert "undocumented-status" not in rules(t + "\n**201.** Создано.\n")


def test_error_in_200():
    t = '# A\n\n#### 200. Successful\n```json\n{"result":"ERROR"}\n```\n'
    assert "error-in-success" in rules(t)
    assert "error-in-success" not in rules(t.replace("ERROR", "OK"))


def test_200_created():
    assert "status-200-created" in rules("# A\n\n#### 200. Successful — Created\nтекст\n")


def test_403_vs_404_is_only_a_question():
    f = rules("# A\n\n#### 403. Forbidden\nДля чужой карты возвращается 404.\n")["status-mismatch"]
    assert f.status == "needs_review"


def test_unfilled_checklist_is_single_finding():
    row = "| Проверка {} | Да / Нет | |\n"
    t = "# A\n\n| Проверка | Отметка | Прим. |\n|---|---|---|\n" + "".join(row.format(i) for i in range(4))
    assert "unfilled-checklist" in rules(t)


def test_placeholder_and_empty_production_url():
    r = rules("# A\n\n## Тестирование\nзаполняются тестировщиками\n\n| Поле | Значение |\n|---|---|\n| Request URL | Dev: `/a` . Prod: — |\n")
    assert "template-placeholder" in r and "missing-url" in r


def test_clean_document_has_no_findings():
    assert rules("# A\n\n* **Ф-1.** Клиент задаёт порог от 1 000 до 5 000 ₸ включительно.\n") == {}


def test_organizer_document_rules(organizer_doc):
    loc = EvidenceLocator(organizer_doc, fallback_requirements(organizer_doc))
    ids = {f.rule_id for f in run_rules(organizer_doc, loc)}
    assert {"get-mutates", "type-mismatch", "content-type-no-body", "undocumented-status", "error-in-success",
            "status-200-created", "status-mismatch", "unfilled-checklist", "template-placeholder", "missing-url"} <= ids
