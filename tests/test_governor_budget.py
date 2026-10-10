from __future__ import annotations

from governor.budget import assemble_budget
from governor.contracts import Candidate
from governor.rerank import ScoredCandidate
from governor.tokenizer import count_tokens


def _item(id_: str, text: str, rank: int = 1) -> ScoredCandidate:
    candidate = Candidate(id=id_, text=text, original_rank=rank)
    return ScoredCandidate(candidate=candidate, scores={"contains_answer_evidence": 0.9})


def test_exact_fit_admits_everything() -> None:
    items = [_item("a", "short one"), _item("b", "short two")]
    total = sum(count_tokens(i.candidate.text) for i in items)

    result = assemble_budget(items, [], token_budget=total, conflict_share=0.0)

    assert [r.item.candidate.id for r in result.accepted] == ["a", "b"]
    assert result.accepted_skipped == []
    assert [r.final_rank for r in result.accepted] == [1, 2]


def test_skip_and_continue() -> None:
    small = _item("small", "tiny")
    huge = _item("huge", "word " * 500)
    also_small = _item("also-small", "tiny too")
    budget = count_tokens(small.candidate.text) + count_tokens(also_small.candidate.text)

    result = assemble_budget([small, huge, also_small], [], token_budget=budget, conflict_share=0.0)

    assert [r.item.candidate.id for r in result.accepted] == ["small", "also-small"]
    assert [i.candidate.id for i in result.accepted_skipped] == ["huge"]


def test_conflict_share_is_reserved_and_not_stolen_by_accepted() -> None:
    accepted_items = [_item(f"acc{i}", "word " * 50) for i in range(10)]
    conflicting_items = [_item("conf1", "short conflict")]

    result = assemble_budget(
        accepted_items, conflicting_items, token_budget=1000, conflict_share=0.25
    )

    # Conflicting evidence got its reserved slice even though accepted evidence
    # alone could have consumed the entire 1000-token budget.
    assert len(result.conflicting) == 1
    assert result.conflicting[0].item.candidate.id == "conf1"
    # Accepted was capped to the remaining 75%, not the full 1000.
    accepted_tokens_used = sum(r.token_count for r in result.accepted)
    assert accepted_tokens_used <= 750


def test_conflict_reserve_unused_is_not_returned_to_accepted() -> None:
    accepted_items = [_item(f"acc{i}", "word " * 50) for i in range(10)]

    result = assemble_budget(accepted_items, [], token_budget=1000, conflict_share=0.25)

    accepted_tokens_used = sum(r.token_count for r in result.accepted)
    assert accepted_tokens_used <= 750


def test_rank_and_token_count_reported_for_every_admitted_passage() -> None:
    items = [_item("a", "one"), _item("b", "two"), _item("c", "three")]
    result = assemble_budget(items, [], token_budget=1000, conflict_share=0.0)

    for expected_rank, r in enumerate(result.accepted, start=1):
        assert r.final_rank == expected_rank
        assert r.token_count == count_tokens(r.item.candidate.text)


def test_zero_budget_admits_nothing() -> None:
    result = assemble_budget([_item("a", "anything")], [], token_budget=0, conflict_share=0.0)
    assert result.accepted == []
    assert len(result.accepted_skipped) == 1


def test_empty_inputs() -> None:
    result = assemble_budget([], [], token_budget=1000, conflict_share=0.25)
    assert result.accepted == []
    assert result.conflicting == []
    assert result.accepted_skipped == []
    assert result.conflicting_skipped == []
