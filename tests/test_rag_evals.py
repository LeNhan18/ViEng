import pytest

from evals.rag import (
    RetrievalCase, check_thresholds, evaluate_retrieval, hit_rate_at_k,
    ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank,
)


def test_single_case_metrics():
    case = RetrievalCase.build("q", ["d2", "d4"], ["d1", "d2", "d3", "d4"])
    assert hit_rate_at_k(case, 1) == 0.0
    assert hit_rate_at_k(case, 2) == 1.0
    assert precision_at_k(case, 2) == 0.5
    assert recall_at_k(case, 2) == 0.5
    assert reciprocal_rank(case) == 0.5
    assert ndcg_at_k(case, 4) == pytest.approx((1 / 1.5849625007 + 1 / 2.3219280949) / (1 + 1 / 1.5849625007))


def test_macro_evaluation_and_thresholds():
    cases = [
        RetrievalCase.build("q1", ["a"], ["a", "x"]),
        RetrievalCase.build("q2", ["b"], ["x", "b"]),
    ]
    metrics = evaluate_retrieval(cases, (1, 2))
    assert metrics["hit_rate@1"] == 0.5
    assert metrics["hit_rate@2"] == 1.0
    assert metrics["mrr"] == 0.75
    checks = check_thresholds(metrics, {"hit_rate@2": 1.0, "mrr": 0.8, "missing": 0.1})
    assert [c["passed"] for c in checks] == [True, False, False]


def test_invalid_cases_fail_fast():
    with pytest.raises(ValueError):
        RetrievalCase.build("q", [], ["a"])
    with pytest.raises(ValueError):
        evaluate_retrieval([])
