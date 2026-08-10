from app.retrieval.fusion import reciprocal_rank_fusion


def test_fusion_prefers_items_in_both_lists():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d", "a"]])

    assert fused[0][0] == "a"
    assert fused[1][0] == "c"


def test_fusion_scores_are_reciprocal():
    fused = reciprocal_rank_fusion([["a"]])

    assert fused == [("a", 1.0 / 61)]


def test_fusion_respects_rank_position():
    fused = reciprocal_rank_fusion([["a", "b"]], k=60)

    score_a = 1.0 / 61
    score_b = 1.0 / 62
    assert fused == [("a", score_a), ("b", score_b)]


def test_fusion_union_with_empty_list():
    fused = reciprocal_rank_fusion([["a"], []])

    assert fused == [("a", 1.0 / 61)]


def test_fusion_no_items():
    assert reciprocal_rank_fusion([[], []]) == []


def test_fusion_uses_k_parameter():
    fused = reciprocal_rank_fusion([["a"]], k=10)

    assert fused == [("a", 1.0 / 11)]
