"""Token-budget assembly with a reserved share for conflicting evidence
: fill the budget greedily, skipping a passage that doesn't
fit and trying the next; conflicting evidence has its own reserved share so
it is never crowded out by accepted evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from governor.rerank import ScoredCandidate
from governor.tokenizer import count_tokens


@dataclass
class RankedEvidence:
    item: ScoredCandidate
    final_rank: int
    token_count: int


@dataclass
class AssembledBudget:
    accepted: list[RankedEvidence]
    accepted_skipped: list[ScoredCandidate]
    conflicting: list[RankedEvidence]
    conflicting_skipped: list[ScoredCandidate]


def _greedy_fill(
    items: list[ScoredCandidate], token_budget: int, tokenizer_name: str
) -> tuple[list[RankedEvidence], list[ScoredCandidate]]:
    filled: list[RankedEvidence] = []
    skipped: list[ScoredCandidate] = []
    used_tokens = 0

    for item in items:
        tokens = count_tokens(item.candidate.text, tokenizer_name)
        if used_tokens + tokens > token_budget:
            skipped.append(item)
            continue
        filled.append(RankedEvidence(item=item, final_rank=len(filled) + 1, token_count=tokens))
        used_tokens += tokens

    return filled, skipped


def assemble_budget(
    accepted_ordered: list[ScoredCandidate],
    conflicting_ordered: list[ScoredCandidate],
    *,
    token_budget: int,
    conflict_share: float,
    tokenizer_name: str = "cl100k_base",
) -> AssembledBudget:
    conflict_budget = round(token_budget * conflict_share)
    accepted_budget = token_budget - conflict_budget

    accepted, accepted_skipped = _greedy_fill(accepted_ordered, accepted_budget, tokenizer_name)
    conflicting, conflicting_skipped = _greedy_fill(
        conflicting_ordered, conflict_budget, tokenizer_name
    )

    return AssembledBudget(
        accepted=accepted,
        accepted_skipped=accepted_skipped,
        conflicting=conflicting,
        conflicting_skipped=conflicting_skipped,
    )
