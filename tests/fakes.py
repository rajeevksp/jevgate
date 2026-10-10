"""Test doubles: no test makes a live Jev call."""

from __future__ import annotations

from jevgate.contracts import Candidate
from jevgate.jev.client import JevJudgmentResult, JevStatus

_ALL_QUESTION_KEYS = [
    "is_relevant",
    "contains_answer_evidence",
    "contradicts_query_premise",
    "contains_prompt_injection",
]


def ok_judgment(candidate_id: str, **scores: float) -> JevJudgmentResult:
    full_scores = dict.fromkeys(_ALL_QUESTION_KEYS, 0.1)
    full_scores.update(scores)
    return JevJudgmentResult(
        candidate_id=candidate_id,
        scores=full_scores,
        model_version="fake/jev-test",
        generation_id="fake-gen",
        tokens_in=50,
        tokens_out=10,
        cost=0.00001,
        latency_ms=5.0,
        attempt_count=1,
        status=JevStatus.OK,
        error=None,
        request_payload={},
        response_payload={},
    )


def unscored_judgment(candidate_id: str) -> JevJudgmentResult:
    return JevJudgmentResult(
        candidate_id=candidate_id,
        scores=None,
        model_version=None,
        generation_id=None,
        tokens_in=None,
        tokens_out=None,
        cost=None,
        latency_ms=5.0,
        attempt_count=3,
        status=JevStatus.UNSCORED,
        error="retries exhausted",
        request_payload={},
        response_payload=None,
    )


def _default_accept_judgment(candidate_id: str) -> JevJudgmentResult:
    """Used where a test doesn't care about specific scores, just that the
    pipeline runs end to end (e.g. chat-pipeline tests retrieving real,
    dynamically-chunked ids from a real ingested PDF)."""
    return ok_judgment(candidate_id, is_relevant=0.9, contains_answer_evidence=0.9)


class FakeJevClient:
    """Deterministic stand-in for the Jev Decisions client. `judgments` maps
    candidate id -> a pre-built JevJudgmentResult (see ok_judgment/
    unscored_judgment above) for tests that care about specific routing;
    anything not in the map falls back to `default_judgment` (an "accept"
    judgment unless overridden), not silently to unscored, so chat-pipeline
    tests against real, dynamically-generated chunk ids still exercise
    governed mode meaningfully without listing every id up front."""

    def __init__(
        self,
        judgments: dict[str, JevJudgmentResult] | None = None,
        default_judgment=_default_accept_judgment,
    ) -> None:
        self.judgments = judgments or {}
        self.default_judgment = default_judgment
        self.calls: list[tuple[str, list[str], str | None]] = []

    async def judge_many(
        self, query: str, candidates: list[Candidate], *, session_id: str | None = None
    ) -> list[JevJudgmentResult]:
        self.calls.append((query, [c.id for c in candidates], session_id))
        return [self.judgments.get(c.id) or self.default_judgment(c.id) for c in candidates]
