from __future__ import annotations

from governor.contracts import Candidate
from governor.rerank import ScoredCandidate, drop_near_duplicates, order_accepted, order_conflicting


def _item(
    id_: str, rank: int, evidence: float, relevance: float, text: str | None = None
) -> ScoredCandidate:
    candidate = Candidate(id=id_, text=text or f"text for {id_}", original_rank=rank)
    return ScoredCandidate(
        candidate=candidate,
        scores={
            "is_relevant": relevance,
            "contains_answer_evidence": evidence,
            "contradicts_query_premise": 0.0,
            "contains_prompt_injection": 0.0,
        },
    )


def test_orders_by_evidence_then_relevance_then_original_rank() -> None:
    a = _item("a", rank=3, evidence=0.9, relevance=0.5)
    b = _item("b", rank=1, evidence=0.9, relevance=0.9)
    c = _item("c", rank=2, evidence=0.5, relevance=0.99)

    ordered = order_accepted([a, b, c])

    # b and a tie on evidence (0.9); b wins on relevance. c has lower evidence, goes last.
    assert [i.candidate.id for i in ordered] == ["b", "a", "c"]


def test_original_rank_breaks_full_ties() -> None:
    a = _item("a", rank=5, evidence=0.7, relevance=0.7)
    b = _item("b", rank=1, evidence=0.7, relevance=0.7)

    ordered = order_accepted([a, b])

    assert [i.candidate.id for i in ordered] == ["b", "a"]


def test_conflicting_ordered_by_original_rank() -> None:
    a = _item("a", rank=3, evidence=0.9, relevance=0.9)
    b = _item("b", rank=1, evidence=0.1, relevance=0.1)

    ordered = order_conflicting([a, b])

    assert [i.candidate.id for i in ordered] == ["b", "a"]


def test_near_duplicate_dropped_keeps_first_higher_priority_copy() -> None:
    first = _item("first", rank=1, evidence=0.9, relevance=0.9, text="The sky is blue today.")
    dup = _item("dup", rank=2, evidence=0.5, relevance=0.5, text="The sky is blue today!")

    kept, dropped = drop_near_duplicates([first, dup], similarity_threshold=0.9)

    assert [i.candidate.id for i in kept] == ["first"]
    assert [i.candidate.id for i in dropped] == ["dup"]


def test_dissimilar_passages_are_both_kept() -> None:
    a = _item("a", rank=1, evidence=0.9, relevance=0.9, text="Completely different content here.")
    b = _item("b", rank=2, evidence=0.5, relevance=0.5, text="Something else entirely unrelated.")

    kept, dropped = drop_near_duplicates([a, b], similarity_threshold=0.9)

    assert {i.candidate.id for i in kept} == {"a", "b"}
    assert dropped == []


def test_three_way_duplicates_keep_only_the_first() -> None:
    text = "Exact same passage text repeated."
    items = [_item(f"c{i}", rank=i, evidence=0.5, relevance=0.5, text=text) for i in range(3)]

    kept, dropped = drop_near_duplicates(items, similarity_threshold=0.9)

    assert [i.candidate.id for i in kept] == ["c0"]
    assert [i.candidate.id for i in dropped] == ["c1", "c2"]


def test_empty_input_produces_empty_output() -> None:
    assert order_accepted([]) == []
    kept, dropped = drop_near_duplicates([])
    assert kept == []
    assert dropped == []
