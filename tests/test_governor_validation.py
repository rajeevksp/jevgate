from __future__ import annotations

from jevgate.contracts import Candidate, GovernorRequest
from jevgate.validation import SetAsideReason, validate_candidates


def _request(candidates: list[Candidate], **kwargs) -> GovernorRequest:
    defaults = {"query": "q", "candidates": candidates, "token_budget": 1000}
    defaults.update(kwargs)
    return GovernorRequest(**defaults)


def test_valid_candidates_pass_through_unchanged() -> None:
    candidates = [Candidate(id="a", text="hello", original_rank=1)]
    result = validate_candidates(_request(candidates), max_passage_chars=100, allow_truncation=True)
    assert [c.id for c in result.eligible] == ["a"]
    assert result.set_aside == []
    assert result.partial_text_ids == set()


def test_missing_id_is_set_aside() -> None:
    candidates = [Candidate(id="", text="hello", original_rank=1)]
    result = validate_candidates(_request(candidates), max_passage_chars=100, allow_truncation=True)
    assert result.eligible == []
    assert result.set_aside[0].reason == SetAsideReason.MISSING_ID


def test_duplicate_id_keeps_first_and_sets_aside_the_rest() -> None:
    candidates = [
        Candidate(id="dup", text="first", original_rank=1),
        Candidate(id="dup", text="second", original_rank=2),
    ]
    result = validate_candidates(_request(candidates), max_passage_chars=100, allow_truncation=True)
    assert [c.id for c in result.eligible] == ["dup"]
    assert result.eligible[0].text == "first"
    assert result.set_aside[0].reason == SetAsideReason.DUPLICATE_ID


def test_empty_text_is_set_aside() -> None:
    candidates = [Candidate(id="a", text="   ", original_rank=1)]
    result = validate_candidates(_request(candidates), max_passage_chars=100, allow_truncation=True)
    assert result.eligible == []
    assert result.set_aside[0].reason == SetAsideReason.EMPTY_TEXT


def test_out_of_scope_id_is_set_aside() -> None:
    candidates = [Candidate(id="a", text="hello", original_rank=1)]
    request = _request(candidates, authorized_ids={"other-id"})
    result = validate_candidates(request, max_passage_chars=100, allow_truncation=True)
    assert result.eligible == []
    assert result.set_aside[0].reason == SetAsideReason.OUT_OF_SCOPE


def test_authorized_id_in_scope_passes() -> None:
    candidates = [Candidate(id="a", text="hello", original_rank=1)]
    request = _request(candidates, authorized_ids={"a", "b"})
    result = validate_candidates(request, max_passage_chars=100, allow_truncation=True)
    assert [c.id for c in result.eligible] == ["a"]


def test_overlong_text_truncated_when_allowed() -> None:
    candidates = [Candidate(id="a", text="x" * 200, original_rank=1)]
    result = validate_candidates(_request(candidates), max_passage_chars=50, allow_truncation=True)
    assert len(result.eligible) == 1
    assert len(result.eligible[0].text) == 50
    assert result.partial_text_ids == {"a"}


def test_overlong_text_set_aside_when_truncation_disallowed() -> None:
    candidates = [Candidate(id="a", text="x" * 200, original_rank=1)]
    result = validate_candidates(_request(candidates), max_passage_chars=50, allow_truncation=False)
    assert result.eligible == []
    assert result.set_aside[0].reason == SetAsideReason.OVER_LENGTH
    assert result.partial_text_ids == set()


def test_transmission_disabled_is_a_request_level_flag_not_a_validation_reason() -> None:
    # allow_external_transmission gates the Jev call itself (governor/P5),
    # not candidate-level validation; validation runs the same either way.
    candidates = [Candidate(id="a", text="hello", original_rank=1)]
    request = _request(candidates, allow_external_transmission=False)
    result = validate_candidates(request, max_passage_chars=100, allow_truncation=True)
    assert [c.id for c in result.eligible] == ["a"]
