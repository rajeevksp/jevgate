"""The governor's evaluate/reroute orchestration.

evaluate() is the only place that calls Jev. reroute() rebuilds a bundle from
already-stored judgments under a (possibly different) policy, with zero new
Jev calls -- both funnel through the same _assemble_from_judgments(), so a
policy change can never produce a different bundle than evaluate() would
have for the same scores.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from jevgate.budget import assemble_budget
from jevgate.bundle import (
    DecisionTrace,
    DecisionTraceEntry,
    EvidenceBundle,
    EvidenceItem,
    ExcludedCandidateItem,
    JudgmentScores,
    NeedsReviewItem,
    UsageAndLatency,
)
from jevgate.contracts import Candidate, GovernorRequest
from jevgate.jev.client import JevClient, JevInsufficientCreditsError, JevJudgmentResult, JevStatus
from jevgate.policy import Policy, Route, route_scores
from jevgate.rerank import ScoredCandidate, drop_near_duplicates, order_accepted, order_conflicting
from jevgate.validation import SetAsideCandidate, ValidationResult, validate_candidates


@dataclass(frozen=True)
class EvaluationConfig:
    max_passage_chars: int
    allow_truncation: bool
    conflict_budget_share: float
    dedup_similarity_threshold: float
    tokenizer_name: str = "cl100k_base"


def _validate(request: GovernorRequest, config: EvaluationConfig) -> ValidationResult:
    return validate_candidates(
        request,
        max_passage_chars=config.max_passage_chars,
        allow_truncation=config.allow_truncation,
    )


async def evaluate(
    request: GovernorRequest,
    jev_client: JevClient,
    policy: Policy,
    config: EvaluationConfig,
    *,
    session_id: str | None = None,
) -> EvidenceBundle:
    if not request.allow_external_transmission:
        return _unavailable_bundle(request.candidates, policy)

    start = time.monotonic()
    validation = _validate(request, config)
    validation_ms = (time.monotonic() - start) * 1000
    if not validation.eligible:
        return EvidenceBundle(
            status="insufficient_evidence",
            excluded_candidates=_excluded_from_set_aside(validation.set_aside),
            decision_trace=_empty_trace(policy),
            usage_and_latency=UsageAndLatency(stage_timings_ms={"validation_ms": validation_ms}),
        )

    start = time.monotonic()
    try:
        judgments = await jev_client.judge_many(
            request.query, validation.eligible, session_id=session_id
        )
    except JevInsufficientCreditsError:
        return _unavailable_bundle(request.candidates, policy)
    jev_ms = (time.monotonic() - start) * 1000

    judgments_by_id = {j.candidate_id: j for j in judgments}
    return _assemble_from_judgments(
        validation.eligible,
        judgments_by_id,
        validation.set_aside,
        validation.partial_text_ids,
        policy,
        config,
        request.token_budget,
        extra_stage_timings={"validation_ms": validation_ms, "jev_evaluation_ms": jev_ms},
    )


def reroute(
    request: GovernorRequest,
    stored_judgments: dict[str, JevJudgmentResult],
    policy: Policy,
    config: EvaluationConfig,
) -> EvidenceBundle:
    """Re-derive routing/rerank/budget for a past run's candidates under a
    (possibly different) policy. Validation is re-run (it's a pure, free
    function of the request) but Jev is never called."""
    validation = _validate(request, config)
    return _assemble_from_judgments(
        validation.eligible,
        stored_judgments,
        validation.set_aside,
        validation.partial_text_ids,
        policy,
        config,
        request.token_budget,
    )


def _assemble_from_judgments(
    eligible: list[Candidate],
    judgments_by_id: dict[str, JevJudgmentResult],
    set_aside: list[SetAsideCandidate],
    partial_text_ids: set[str],
    policy: Policy,
    config: EvaluationConfig,
    token_budget: int,
    extra_stage_timings: dict[str, float] | None = None,
) -> EvidenceBundle:
    start = time.monotonic()
    accepted_scored: list[ScoredCandidate] = []
    conflicting_scored: list[ScoredCandidate] = []
    excluded_items: list[ExcludedCandidateItem] = _excluded_from_set_aside(set_aside)
    needs_review_items: list[NeedsReviewItem] = []
    trace_entries: list[DecisionTraceEntry] = []
    any_unscored_or_failed = False

    for candidate in eligible:
        judgment = judgments_by_id.get(candidate.id)
        if judgment is None or judgment.status != JevStatus.OK:
            any_unscored_or_failed = True
            reason = "payload_too_large" if judgment and judgment.payload_too_large else "unscored"
            needs_review_items.append(NeedsReviewItem(id=candidate.id, reason=reason))
            trace_entries.append(
                DecisionTraceEntry(
                    id=candidate.id,
                    jev_status=str(judgment.status) if judgment else "missing",
                )
            )
            continue

        if candidate.id in partial_text_ids:
            needs_review_items.append(NeedsReviewItem(id=candidate.id, reason="truncated"))

        scores = JudgmentScores(**judgment.scores)
        decision = route_scores(judgment.scores, policy)
        trace_entries.append(
            DecisionTraceEntry(
                id=candidate.id, scores=scores, rule_fired=decision.rule_fired, jev_status="ok"
            )
        )
        scored = ScoredCandidate(candidate=candidate, scores=judgment.scores)

        if decision.route == Route.ACCEPT:
            accepted_scored.append(scored)
        elif decision.route == Route.CONFLICT:
            conflicting_scored.append(scored)
        else:  # EXCLUDE or WITHHOLD -- both leave the answer context
            if decision.route == Route.WITHHOLD and decision.needs_review_overlap:
                needs_review_items.append(
                    NeedsReviewItem(id=candidate.id, reason="injection_contradiction_overlap")
                )
            excluded = ExcludedCandidateItem(
                id=candidate.id, rule_fired=decision.rule_fired, scores=scores
            )
            excluded_items.append(excluded)

    accepted_ordered = order_accepted(accepted_scored)
    accepted_kept, accepted_dupes = drop_near_duplicates(
        accepted_ordered, config.dedup_similarity_threshold
    )
    conflicting_ordered = order_conflicting(conflicting_scored)
    conflicting_kept, conflicting_dupes = drop_near_duplicates(
        conflicting_ordered, config.dedup_similarity_threshold
    )
    for dupe in accepted_dupes + conflicting_dupes:
        excluded_items.append(
            ExcludedCandidateItem(
                id=dupe.candidate.id,
                rule_fired="near_duplicate",
                scores=JudgmentScores(**dupe.scores),
            )
        )
    routing_ms = (time.monotonic() - start) * 1000

    start = time.monotonic()
    assembled = assemble_budget(
        accepted_kept,
        conflicting_kept,
        token_budget=token_budget,
        conflict_share=config.conflict_budget_share,
        tokenizer_name=config.tokenizer_name,
    )
    budget_ms = (time.monotonic() - start) * 1000

    for skipped in assembled.accepted_skipped + assembled.conflicting_skipped:
        excluded_items.append(
            ExcludedCandidateItem(
                id=skipped.candidate.id,
                rule_fired="budget_exhausted",
                scores=JudgmentScores(**skipped.scores),
            )
        )

    accepted_evidence = [
        EvidenceItem(
            id=r.item.candidate.id,
            text=r.item.candidate.text,
            source_location=r.item.candidate.source_location,
            original_rank=r.item.candidate.original_rank,
            final_rank=r.final_rank,
            token_count=r.token_count,
            scores=JudgmentScores(**r.item.scores),
        )
        for r in assembled.accepted
    ]
    conflicting_evidence = [
        EvidenceItem(
            id=r.item.candidate.id,
            text=r.item.candidate.text,
            source_location=r.item.candidate.source_location,
            original_rank=r.item.candidate.original_rank,
            final_rank=r.final_rank,
            token_count=r.token_count,
            scores=JudgmentScores(**r.item.scores),
        )
        for r in assembled.conflicting
    ]

    if not accepted_evidence and not conflicting_evidence:
        status = "insufficient_evidence"
    elif any_unscored_or_failed:
        status = "partial"
    else:
        status = "ok"

    stage_timings = {"routing_rerank_ms": routing_ms, "budget_assembly_ms": budget_ms}
    stage_timings.update(extra_stage_timings or {})

    usage = UsageAndLatency(
        jev_requests=len(judgments_by_id),
        jev_input_tokens=sum(j.tokens_in or 0 for j in judgments_by_id.values()),
        jev_output_tokens=sum(j.tokens_out or 0 for j in judgments_by_id.values()),
        jev_cost=sum(j.cost or 0.0 for j in judgments_by_id.values()),
        jev_retries=sum(max(j.attempt_count - 1, 0) for j in judgments_by_id.values()),
        stage_timings_ms=stage_timings,
    )

    return EvidenceBundle(
        status=status,
        accepted_evidence=accepted_evidence,
        conflicting_evidence=conflicting_evidence,
        excluded_candidates=excluded_items,
        needs_review=needs_review_items,
        decision_trace=DecisionTrace(
            policy_name=policy.name,
            policy_version=policy.version,
            question_set_version=policy.question_set_version,
            entries=trace_entries,
        ),
        usage_and_latency=usage,
    )


def _excluded_from_set_aside(set_aside: list[SetAsideCandidate]) -> list[ExcludedCandidateItem]:
    return [ExcludedCandidateItem(id=s.candidate.id, rule_fired=str(s.reason)) for s in set_aside]


def _empty_trace(policy: Policy) -> DecisionTrace:
    return DecisionTrace(
        policy_name=policy.name,
        policy_version=policy.version,
        question_set_version=policy.question_set_version,
    )


def _unavailable_bundle(candidates: list[Candidate], policy: Policy) -> EvidenceBundle:
    ordered = sorted(candidates, key=lambda c: c.original_rank)
    return EvidenceBundle(
        status="evaluation_unavailable",
        needs_review=[NeedsReviewItem(id=c.id, reason="unevaluated") for c in ordered],
        decision_trace=_empty_trace(policy),
    )
