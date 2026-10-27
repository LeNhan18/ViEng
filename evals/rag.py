"""Deterministic, dependency-free RAG retrieval evaluation metrics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    relevant_ids: frozenset[str]
    retrieved_ids: tuple[str, ...]

    @classmethod
    def build(cls, query: str, relevant_ids: Iterable[str], retrieved_ids: Sequence[str]):
        relevant = frozenset(str(x) for x in relevant_ids)
        if not relevant:
            raise ValueError("relevant_ids must not be empty")
        return cls(query, relevant, tuple(str(x) for x in retrieved_ids))


def _top(case: RetrievalCase, k: int) -> tuple[str, ...]:
    if k <= 0:
        raise ValueError("k must be > 0")
    return case.retrieved_ids[:k]


def hit_rate_at_k(case: RetrievalCase, k: int) -> float:
    return float(any(x in case.relevant_ids for x in _top(case, k)))


def precision_at_k(case: RetrievalCase, k: int) -> float:
    top = _top(case, k)
    return sum(x in case.relevant_ids for x in top) / len(top) if top else 0.0


def recall_at_k(case: RetrievalCase, k: int) -> float:
    return len(set(_top(case, k)) & case.relevant_ids) / len(case.relevant_ids)


def reciprocal_rank(case: RetrievalCase, k: int | None = None) -> float:
    ranked = case.retrieved_ids if k is None else _top(case, k)
    for rank, doc_id in enumerate(ranked, 1):
        if doc_id in case.relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(case: RetrievalCase, k: int) -> float:
    top = _top(case, k)
    dcg = sum(1.0 / math.log2(rank + 1) for rank, doc_id in enumerate(top, 1) if doc_id in case.relevant_ids)
    ideal_hits = min(len(case.relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def evaluate_retrieval(cases: Sequence[RetrievalCase], k_values: Sequence[int] = (1, 3, 5)) -> dict[str, float]:
    if not cases:
        raise ValueError("cases must not be empty")
    ks = tuple(dict.fromkeys(int(k) for k in k_values))
    if not ks or any(k <= 0 for k in ks):
        raise ValueError("k_values must contain positive integers")
    avg = lambda xs: sum(xs) / len(xs)
    metrics = {"mrr": avg([reciprocal_rank(c) for c in cases])}
    for k in ks:
        metrics[f"hit_rate@{k}"] = avg([hit_rate_at_k(c, k) for c in cases])
        metrics[f"precision@{k}"] = avg([precision_at_k(c, k) for c in cases])
        metrics[f"recall@{k}"] = avg([recall_at_k(c, k) for c in cases])
        metrics[f"ndcg@{k}"] = avg([ndcg_at_k(c, k) for c in cases])
    return metrics


def check_thresholds(metrics: dict[str, float], thresholds: dict[str, float]) -> list[dict]:
    return [{"metric": name, "value": metrics.get(name), "minimum": float(minimum),
             "passed": metrics.get(name) is not None and metrics[name] >= float(minimum)}
            for name, minimum in thresholds.items()]
