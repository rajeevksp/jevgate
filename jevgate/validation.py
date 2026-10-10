"""Validation before any Jev call: duplicate/missing ids,
empty or over-length text, out-of-scope ids. Invalid or unauthorized records
never reach Jev (L1-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jevgate.contracts import Candidate, GovernorRequest


class SetAsideReason(StrEnum):
    MISSING_ID = "missing_id"
    DUPLICATE_ID = "duplicate_id"
    EMPTY_TEXT = "empty_text"
    OVER_LENGTH = "over_length"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class SetAsideCandidate:
    candidate: Candidate
    reason: SetAsideReason


@dataclass
class ValidationResult:
    eligible: list[Candidate]
    set_aside: list[SetAsideCandidate]
    partial_text_ids: set[str]


def validate_candidates(
    request: GovernorRequest,
    *,
    max_passage_chars: int,
    allow_truncation: bool,
) -> ValidationResult:
    eligible: list[Candidate] = []
    set_aside: list[SetAsideCandidate] = []
    partial_text_ids: set[str] = set()
    seen_ids: set[str] = set()

    for candidate in request.candidates:
        if not candidate.id:
            set_aside.append(SetAsideCandidate(candidate, SetAsideReason.MISSING_ID))
            continue
        if candidate.id in seen_ids:
            set_aside.append(SetAsideCandidate(candidate, SetAsideReason.DUPLICATE_ID))
            continue
        seen_ids.add(candidate.id)

        if not candidate.text or not candidate.text.strip():
            set_aside.append(SetAsideCandidate(candidate, SetAsideReason.EMPTY_TEXT))
            continue

        if request.authorized_ids is not None and candidate.id not in request.authorized_ids:
            set_aside.append(SetAsideCandidate(candidate, SetAsideReason.OUT_OF_SCOPE))
            continue

        if len(candidate.text) > max_passage_chars:
            if not allow_truncation:
                set_aside.append(SetAsideCandidate(candidate, SetAsideReason.OVER_LENGTH))
                continue
            candidate = candidate.model_copy(update={"text": candidate.text[:max_passage_chars]})
            partial_text_ids.add(candidate.id)

        eligible.append(candidate)

    return ValidationResult(
        eligible=eligible, set_aside=set_aside, partial_text_ids=partial_text_ids
    )
