"""Оценка качества: синтетический golden dataset и список дефектов выданного документа.

python -m app.evaluate --dataset            прогон 4 документов (около 8 вызовов модели на каждый)
python -m app.evaluate --dataset --rules-only
python -m app.evaluate --report output/report.json   сверка готового отчёта с docs/golden/organizer.json
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import CACHE_DIR, ROOT, get_settings
from .llm.cache import ResponseCache
from .llm.openrouter import make_llm
from .parser import parse_document
from .pipeline import analyze

GOLDEN = ROOT / "docs" / "golden"


def load_cases() -> list[dict]:
    return [json.loads(l) for l in (GOLDEN / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def metrics(tp, fp, fn) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (None if p is None or r is None else 0.0)
    return {"precision": p, "recall": r, "f1": round(f1, 4) if f1 is not None else None}


def evaluate_cases(cases, spans, findings) -> dict:
    """Кейс засчитан, если замечание допустимой категории опирается на его фрагмент.
    На корректном кейсе любое подтверждённое замечание — ложное срабатывание."""
    c = dict(tp=0, fp=0, fn=0, tn=0)
    details = []
    for case in cases:
        lo, hi = spans[case["test_id"]]
        own = [f for f in findings if any(lo <= s and e <= hi for s, e in f["spans"])]
        if case["expected_detection"]:
            hit = any(f["category"] in case.get("accept", [case["category"]]) for f in own)
            result = "tp" if hit else "fn"
        else:
            result = "fp" if own else "tn"
        c[result] += 1
        details.append({"test_id": case["test_id"], "result": result, "found": [f["category"] for f in own]})
    return {"counts": c, "metrics": metrics(c["tp"], c["fp"], c["fn"]), "details": details}


def build_group(group: str, cases: list[dict]) -> str:
    out = f"# Тестовый набор: {group}\n\nКаждый раздел — отдельный независимый продукт.\n"
    for c in cases:
        out += f"\n## Продукт {c['test_id']}\n\n{c['input']}\n"
    return out


async def run_dataset(llm, timeout) -> dict:
    all_cases, all_findings, spans, shift, partial, models = load_cases(), [], {}, 0, [], set()
    names = sorted({c["group"] for c in all_cases})
    for i in range(0, len(names), 2):  # по две группы в документе: меньше запросов
        pair = names[i:i + 2]
        group, items = " и ".join(pair), [c for c in all_cases if c["group"] in pair]
        text = build_group(group, items)
        for c in items:
            at = text.index(c["input"])
            spans[c["test_id"]] = (shift + at, shift + at + len(c["input"]))
        r = await analyze(parse_document(f"{group}.md", text.encode()), llm, timeout=timeout)
        models.add(r.model_name)
        if r.status != "completed":
            partial.append(group)
        all_findings += [{"category": f.category, "spans": [(shift + e.start, shift + e.end) for e in f.evidence]}
                         for f in r.findings if f.status == "confirmed"]
        shift += len(text) + 1000
        print(f"{group}: {r.status}, замечаний {len(r.findings)}", file=sys.stderr)
    return {**evaluate_cases(all_cases, spans, all_findings), "models": sorted(models), "sample_size": len(all_cases), "partial_groups": partial}


def check_report(path: Path) -> dict:
    """Дефект найден, если замечание цитирует хотя бы один якорный фрагмент и содержит одно из ключевых слов."""
    r = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for d in json.loads((GOLDEN / "organizer.json").read_text(encoding="utf-8")):
        hit = [f["id"] for f in r["findings"]
               if any(a.lower() in e["quote"].lower() or (len(e["quote"]) >= 10 and e["quote"].lower() in a.lower()) for a in d["anchors"] for e in f["evidence"])
               and any(k in " ".join((f["title"], f["explanation"], f["recommendation"])).lower() for k in d["keywords"])]
        rows.append({"id": d["id"], "title": d["title"], "found": hit})
    text = r["document_text"]
    quotes = [e for f in r["findings"] for e in f["evidence"]]
    return {"found": sum(bool(x["found"]) for x in rows), "total": len(rows),
            "quotes_valid": all(text[e["start"]:e["end"]] == e["quote"] for e in quotes),
            "evidence_coverage": all(f["evidence"] for f in r["findings"]), "defects": rows}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", action="store_true")
    p.add_argument("--rules-only", action="store_true")
    p.add_argument("--cache", action="store_true")
    p.add_argument("--report", type=Path)
    a = p.parse_args(argv)
    if a.report:
        out = check_report(a.report)
    elif a.dataset:
        s = get_settings()
        llm = None if a.rules_only else make_llm(s, ResponseCache(CACHE_DIR) if a.cache else None)
        if llm is None and not a.rules_only:
            print("Не задан ключ модели: OPENROUTER_API_KEY или GEMINI_API_KEY.", file=sys.stderr)
            return 1
        out = asyncio.run(run_dataset(llm, s.analysis_timeout))
    else:
        p.print_help()
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
