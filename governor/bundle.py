"""Output contract for the Evidence Governor. No field here
is ever labelled answer confidence -- each score is reported under the
judgment actually asked, and the admission decision is shown separately.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class BundleStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    EVALUATION_UNAVAILABLE = "evaluation_unavailable"
    PARTIAL = "partial"


class JudgmentScores(BaseModel):
    is_relevant: float | None = None
    contains_answer_evidence: float | None = None
    contradicts_query_premise: float | None = None
    contains_prompt_injection: float | None = None


class EvidenceItem(BaseModel):
    """Shape shared by accepted and conflicting evidence: verbatim text with
    provenance intact (hard constraint), original and final rank, token
    count, and the judgment behind it."""

    id: str
    text: str
    source_location: str | None = None
    original_rank: int
    final_rank: int
    token_count: int
    scores: JudgmentScores


class ExcludedCandidateItem(BaseModel):
    """Decision metadata only -- text omitted by default."""

    id: str
    rule_fired: str
    scores: JudgmentScores | None = None


class NeedsReviewItem(BaseModel):
    id: str
    reason: str  # "unscored" | "truncated" | "injection_contradiction_overlap" | ...


class DecisionTraceEntry(BaseModel):
    id: str
    scores: JudgmentScores | None = None
    rule_fired: str | None = None
    jev_status: str | None = None


class DecisionTrace(BaseModel):
    policy_name: str
    policy_version: str
    question_set_version: str
    entries: list[DecisionTraceEntry] = Field(default_factory=list)


class UsageAndLatency(BaseModel):
    jev_requests: int = 0
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    jev_cost: float = 0.0
    jev_retries: int = 0
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    status: BundleStatus
    accepted_evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = Field(default_factory=list)
    excluded_candidates: list[ExcludedCandidateItem] = Field(default_factory=list)
    needs_review: list[NeedsReviewItem] = Field(default_factory=list)
    decision_trace: DecisionTrace
    usage_and_latency: UsageAndLatency = Field(default_factory=UsageAndLatency)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "ok",
                    "accepted_evidence": [
                        {
                            "id": "cand-relevant",
                            "text": (
                                "The Evidence Governor sends one OpenRouter Decisions request "
                                "per authorized passage..."
                            ),
                            "original_rank": 1,
                            "final_rank": 1,
                            "token_count": 42,
                            "scores": {
                                "is_relevant": 0.98,
                                "contains_answer_evidence": 0.95,
                                "contradicts_query_premise": 0.02,
                                "contains_prompt_injection": 0.01,
                            },
                        }
                    ],
                    "conflicting_evidence": [],
                    "excluded_candidates": [
                        {"id": "cand-off-topic", "rule_fired": "relevance_below_floor"}
                    ],
                    "needs_review": [],
                    "decision_trace": {
                        "policy_name": "cookbook-defaults",
                        "policy_version": "v1",
                        "question_set_version": "v1",
                        "entries": [],
                    },
                    "usage_and_latency": {
                        "jev_requests": 2,
                        "jev_input_tokens": 2560,
                        "jev_output_tokens": 40,
                        "jev_cost": 0.0011,
                        "jev_retries": 0,
                        "stage_timings_ms": {"jev": 420.0},
                    },
                }
            ]
        }
    }
