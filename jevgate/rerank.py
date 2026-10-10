"""Rerank accepted (and conflicting) evidence, and drop near-duplicates
: order by answer evidence, then relevance, then original
rank; a passage judged a near-duplicate of an already-kept, higher-priority
passage is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from jevgate.contracts import Candidate


@dataclass
class ScoredCandidate:
    candidate: Candidate
    scores: dict[str, float]


def order_accepted(items: list[ScoredCandidate]) -> list[ScoredCandidate]:
    return sorted(
        items,
        key=lambda i: (
            -i.scores.get("contains_answer_evidence", 0.0),
            -i.scores.get("is_relevant", 0.0),
            i.candidate.original_rank,
        ),
    )


def order_conflicting(items: list[ScoredCandidate]) -> list[ScoredCandidate]:
    # Only an ordering for accepted evidence; original rank
    # is the simplest deterministic default for the conflicting block.
    return sorted(items, key=lambda i: i.candidate.original_rank)


def drop_near_duplicates(
    items: list[ScoredCandidate], similarity_threshold: float = 0.9
) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    """items must already be in priority order -- the first occurrence of a
    near-duplicate pair is kept, matching "keeping the higher-ranked copy"."""
    kept: list[ScoredCandidate] = []
    dropped: list[ScoredCandidate] = []
    normalized_kept: list[str] = []

    for item in items:
        candidate_norm = _normalize(item.candidate.text)
        is_duplicate = any(
            SequenceMatcher(None, candidate_norm, kept_norm).ratio() >= similarity_threshold
            for kept_norm in normalized_kept
        )
        if is_duplicate:
            dropped.append(item)
        else:
            kept.append(item)
            normalized_kept.append(candidate_norm)

    return kept, dropped


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())
