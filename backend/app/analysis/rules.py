"""Детерминированные проверки. Каждая срабатывает только на явных признаках в тексте."""
import re
from itertools import groupby

from ..models import Document, Finding, Segment
from .evidence import EvidenceLocator

WRITE = re.compile(r"\b(сохран(ение|ить|яет)|измен(ение|ить|яет)|удал(ение|ить|яет)|созда(ние|ть|ет|ёт)|обнов(ление|ить|ляет)|замен(а|ить|яет))\b", re.I)
READ = re.compile(r"\b(чтени[ея]|получени[ея]|прочитать|просмотр)\b", re.I)
WRITE_URL = re.compile(r"/(save|update|delete|create|remove|set)(?=[A-Z_\-/`'\"\s?.,;:)]|$)")
GET_LINE = re.compile(r"\bGET\s+`?\S*/(save|update|delete|create|remove|set)(?=[A-Z_\-/`'\"\s?.,;:)]|$)")
STATUS_START = re.compile(r"^[#*\s|`]*([1-5]\d\d)\b")
PLACEHOLDER = re.compile(r"\b(TBD|TODO|будет заполнено|заполня(ю|е)тся (позже|далее|\w+ами)|заполнить позже)\b|^\W*уточняется\W*$", re.I)
TYPES = {"integer": "integer", "int": "integer", "number": "number", "string": "string", "str": "string",
         "boolean": "boolean", "bool": "boolean", "целое": "integer", "строка": "string"}


def run_rules(doc: Document, locator: EvidenceLocator) -> list[Finding]:
    out: list[Finding] = []
    segs = doc.segments

    def add(rule_id, title, category, criterion, severity, where: list[Segment], explanation, impact, recommendation,
            status="confirmed", is_gap=False):
        evidence = [locator.from_segment(s) for s in where]
        out.append(Finding(
            id=f"RULE-{len(out) + 1:03}", rule_id=rule_id, title=title, category=category, criteria=[criterion],
            severity=severity, confidence=1.0 if status == "confirmed" else 0.6, evidence=evidence,
            requirement_ids=list(dict.fromkeys(e.requirement_id for e in evidence if e.requirement_id)),
            explanation=explanation, impact=impact, recommendation=recommendation, status=status,
            source="rule", is_gap=is_gap, stage="structure_rules"))

    def last_heading(s):
        return s.section.rsplit(" / ", 1)[-1]

    tables = [list(g) for _, g in groupby((s for s in segs if s.kind == "table_row"),
                                          key=lambda s: (s.section, tuple(s.columns)))]
    for rows in tables:
        fields = {r.cells[0].lower(): r for r in rows if len(r.cells) >= 2}
        method = next((r for k, r in fields.items() if k in ("rest type", "method", "метод", "http method", "http-метод")), None)
        is_get = method is not None and method.cells[1].upper() == "GET"
        desc = next((r for k, r in fields.items() if k in ("description", "описание")), None)
        urls = [r for k, r in fields.items() if "url" in k and WRITE_URL.search(r.text)]
        writes = [r for r in (desc,) if r and WRITE.search(r.cells[1])] + urls
        reads_only = desc is not None and READ.search(desc.cells[1]) and not WRITE.search(desc.cells[1])
        if is_get and writes and not reads_only:
            add("get-mutates", "Метод GET используется для изменения данных", "api_design", "correct", "high",
                [method, *writes],
                f"Метод объявлен как GET, но {'описание' if desc in writes else 'адрес'} говорит об изменении данных. "
                "По RFC 9110 GET — безопасный метод и не должен менять состояние.",
                "Кеш, предзагрузка или автоматический повтор запроса могут изменить настройку без действия клиента; параметры попадают в журналы.",
                "Использовать для сохранения PUT или POST (PATCH при частичном изменении), чтение вынести в отдельный GET.")
        if desc and WRITE.search(desc.cells[1]) and READ.search(desc.cells[1]):
            add("mixed-description", "Описание одного метода совмещает сохранение и чтение", "inconsistency", "consistent", "high",
                [desc, method] if method else [desc],
                "В поле описания один метод назван и сохранением, и чтением.",
                "Неясно, какую операцию реализует метод; контракт второй операции отсутствует.",
                "Описать чтение и сохранение как два метода с отдельными контрактами.")
        for k, r in fields.items():
            if "url" in k and (re.search(r"prod\w*\s*:\s*[—–-]", r.text, re.I) or
                               ("prod" in k and r.cells[1] in ("", "—", "-", "–"))):
                add("missing-url", "Не задан адрес для Prod", "incompleteness", "complete", "medium", [r],
                    "Для промышленной среды вместо адреса стоит прочерк.",
                    "Метод нельзя подключить и проверить в промышленной среде.",
                    "Указать адрес Prod или правило его формирования.", is_gap=True)
        boxes = [r for r in rows if any(re.fullmatch(r"Да / Нет( / Не требуется)?", c) for c in r.cells)]
        if len(boxes) >= 3:
            add("unfilled-checklist", f"Чек-лист не заполнен: {len(boxes)} пунктов без отметок", "incompleteness", "complete",
                "low", boxes[:3], "В пунктах остались варианты из шаблона «Да / Нет», выбор не сделан.",
                "Нет подтверждения, что ревью требований проведено.", "Заполнить отметки и указать версию проверенного документа.",
                is_gap=True)

    for s in segs:
        if s.kind not in ("heading", "table_row") and GET_LINE.search(s.text):
            add("get-mutates", "Метод GET используется для изменения данных", "api_design", "correct", "high", [s],
                "Адрес метода GET обозначает изменение данных. По RFC 9110 GET не должен менять состояние.",
                "Кеш или повтор запроса могут изменить данные без действия клиента.", "Использовать PUT, POST или DELETE.")
        if s.kind in ("paragraph", "list_item") and PLACEHOLDER.search(s.text) and len(s.text) < 120:
            mark = re.search(r"\b(TBD|TODO)\b", s.text)
            if mark and len(s.text.split()) > 4:  # требование написано, не определена его часть
                add("template-placeholder", f"Значение не определено: {mark[1]}", "incompleteness", "complete",
                    "medium", [s], f"В тексте на месте значения стоит пометка {mark[1]}.",
                    "Требование нельзя реализовать и проверить без этого значения.",
                    "Указать значение или согласовать срок его определения.", is_gap=True)
            else:
                add("template-placeholder", f"Раздел «{last_heading(s)}» оставлен заглушкой", "incompleteness", "complete",
                    "medium", [s], "Вместо содержания оставлена фраза шаблона.",
                    "Раздел нельзя использовать как основание для разработки и тестирования.",
                    "Заполнить раздел либо указать, почему он не требуется.", is_gap=True)

    params: dict[str, list[tuple[Segment, str]]] = {}
    for s in segs:
        if s.kind != "table_row" or len(s.cells) < 2 or not s.columns:
            continue
        col = next((i for i, c in enumerate(s.columns) if c.lower() in ("format", "type", "формат", "тип")), None)
        if col and col < len(s.cells) and s.columns[0].lower() in ("parameter", "параметр", "поле", "field", "name", "имя"):
            kind = TYPES.get(s.cells[col].lower().split()[0] if s.cells[col] else "")
            if kind:
                params.setdefault(s.cells[0], []).append((s, kind))
    for name, uses in params.items():
        other = next((u for u in uses[1:] if u[1] != uses[0][1]), None)
        if other:
            first = uses[0]
            # в одном методе запрос и ответ обязаны совпадать; в разных методах поле может значить разное
            same_method = first[0].section == other[0].section or any(re.search(r"запрос|ответ|параметр|request|response|query|body", last_heading(u[0]), re.I) for u in (first, other))
            add("type-mismatch", f"Поле {name} имеет разные типы: {first[1]} и {other[1]}", "data_quality", "consistent", "medium",
                [first[0], other[0]],
                f"В разделе «{last_heading(first[0])}» тип поля {name} — {first[1]}, в разделе «{last_heading(other[0])}» — {other[1]}.",
                "Клиент и сервер по-разному разберут значение; возможны ошибки преобразования.",
                "Задать один тип поля во всём контракте или явно описать преобразование.",
                status="confirmed" if same_method else "needs_review")

    for a in segs:
        if re.search(r"content-type", a.text, re.I) and "json" in a.text.lower():
            b = next((s for s in segs if s.section == a.section and re.search(r"тело\s+(запроса\s+)?не\s+используется", s.text, re.I)), None)
            if b:
                add("content-type-no-body", "Указан Content-Type, хотя тела запроса нет", "api_design", "consistent", "low",
                    [a] if a is b else [a, b], "Раздел задаёт Content-Type тела запроса и одновременно говорит, что тело не используется.",
                    "Неясно, передаются ли параметры в теле или в адресе.", "Убрать Content-Type либо описать тело запроса.")

    documented = {m[1] for s in segs if (m := STATUS_START.match(s.text))}
    for s in segs:
        if not documented or s.kind not in ("paragraph", "list_item"):
            continue
        for sentence in re.split(r"(?<=[.;])\s", s.text):
            if not re.search(r"(?<!не)успеш", sentence, re.I):
                continue
            missing = [c for c in re.findall(r"(?<!\d)[23]\d\d(?!\s?[\d₸%])", sentence) if c not in documented]
            if missing and re.search(r"\b(код|статус|результат|ответ|http)", sentence, re.I) and not STATUS_START.match(s.text):
                add("undocumented-status", f"Код {', '.join(missing)} назван успешным, но не описан", "incompleteness", "complete",
                    "medium", [s], f"Код {', '.join(missing)} упомянут как успешный результат, но отдельного описания и примера ответа нет.",
                    "Неясно, когда возвращается этот код и какое у него тело.", "Описать условие и тело ответа либо убрать код.", is_gap=True)

    for s in segs:
        head = STATUS_START.match(last_heading(s))
        if s.kind == "code" and head and head[1][0] == "2" and re.search(r"\b(ERROR|FAIL(ED)?)\b", s.text):
            h = [x for x in segs if x.kind == "heading" and x.section == s.section][-1:]
            add("error-in-success", f"Ответ с ошибкой возвращается с кодом {head[1]}", "api_design", "consistent", "high", [*h, s],
                f"В примере для кода {head[1]} показан ответ с результатом ERROR.",
                "Клиент и мониторинг по коду ответа посчитают неудачную операцию успешной.",
                "Возвращать ошибки проверки с кодом 4xx либо явно закрепить правило «ошибка в теле» и согласовать его с остальными кодами.")
        if s.kind == "heading" and re.search(r"\b200\b.*\bcreated\b", s.text, re.I):
            add("status-200-created", "Код 200 назван Created", "api_design", "consistent", "low", [s],
                "Created — название кода 201, а заголовок описывает 200.", "Неясно, какой код должен вернуть сервис.",
                "Указать «200 OK» или «201 Created».")
        if s.kind == "paragraph" and head and head[1][0] in "45":
            codes = set(re.findall(r"(?<!\d)[45]\d\d(?!\d)", s.text)) - {head[1]}
            if codes and re.search(r"возвраща", s.text, re.I):
                h = [x for x in segs if x.kind == "heading" and x.section == s.section][-1:]
                code = sorted(codes)[0]
                add("status-mismatch", f"В разделе {head[1]} описан возврат {code}", "inconsistency", "consistent", "medium", [*h, s],
                    f"Раздел посвящён коду {head[1]}, но правило внутри него требует {code}. Возврат {code} может быть осознанным сокрытием существования ресурса.",
                    f"Неясно, в каком случае возвращается {head[1]}.", f"Уточнить у аналитика, когда применяется {head[1]}, а когда {code}.",
                    status="needs_review")
    return out
