from app.evaluate import evaluate_cases, load_cases, metrics


def test_dataset_shape():
    cases = load_cases()
    pos = [c for c in cases if c["expected_detection"]]
    assert len(pos) == 40 and len(cases) - len(pos) >= 8
    assert len({c["test_id"] for c in cases}) == len(cases)
    assert all(c["expected_evidence"] in c["input"] for c in pos)


def test_metrics():
    m = metrics(8, 2, 2)
    assert m == {"precision": .8, "recall": .8, "f1": .8}
    assert metrics(0, 0, 0)["precision"] is None


def test_case_scored_by_evidence_position():
    cases = [dict(test_id="1", category="api_design", group="API", input="GET /saveLimit меняет", expected_detection=True, expected_evidence="GET /saveLimit", accept=["api_design"]),
             dict(test_id="2", category="api_design", group="API", input="GET /limit читает", expected_detection=False, expected_evidence="")]
    spans = {"1": (0, 30), "2": (40, 70)}
    findings = [dict(category="api_design", spans=[(2, 10)]), dict(category="ambiguity", spans=[(45, 50)])]
    assert evaluate_cases(cases, spans, findings)["counts"] == {"tp": 1, "fp": 1, "fn": 0, "tn": 0}
