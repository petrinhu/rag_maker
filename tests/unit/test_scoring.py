from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rag_maker.domain.scoring import rrf_fuse


@pytest.mark.unit
class TestRrfFuse:
    def test_empty_inputs(self) -> None:
        assert rrf_fuse([], []) == {}

    def test_single_list(self) -> None:
        result = rrf_fuse(["a", "b", "c"], [])
        assert set(result.keys()) == {"a", "b", "c"}
        assert result["a"] > result["b"] > result["c"], "rank 1 deve ter score maior"

    def test_both_lists_union(self) -> None:
        result = rrf_fuse(["a", "b"], ["b", "c"])
        assert set(result.keys()) == {"a", "b", "c"}

    def test_chunk_in_both_lists_has_higher_score(self) -> None:
        result = rrf_fuse(["shared", "only_dense"], ["shared", "only_lex"])
        assert result["shared"] > result["only_dense"]
        assert result["shared"] > result["only_lex"]

    def test_scores_all_positive(self) -> None:
        result = rrf_fuse(["x", "y"], ["y", "z"])
        assert all(v > 0 for v in result.values())

    def test_custom_k(self) -> None:
        r1 = rrf_fuse(["a"], [], k=60)
        r2 = rrf_fuse(["a"], [], k=1)
        assert r2["a"] > r1["a"], "k menor → score maior"


@pytest.mark.unit
@settings(max_examples=50)
@given(
    ids_a=st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=15, unique=True),
    ids_b=st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=15, unique=True),
    k=st.integers(min_value=1, max_value=120),
)
def test_rrf_scores_positive_hypothesis(ids_a: list[str], ids_b: list[str], k: int) -> None:
    result = rrf_fuse(ids_a, ids_b, k=k)
    assert all(v > 0 for v in result.values())


@pytest.mark.unit
@settings(max_examples=50)
@given(
    ids=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=20, unique=True),
)
def test_rrf_rank_monotonicity_hypothesis(ids: list[str]) -> None:
    result = rrf_fuse(ids, [])
    scores = [result[cid] for cid in ids]
    assert scores == sorted(scores, reverse=True), "score deve ser decrescente por rank"
