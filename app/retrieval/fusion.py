from __future__ import annotations

from collections import defaultdict

RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    *,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            scores[item] += 1.0 / (k + rank + 1)
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return ordered
