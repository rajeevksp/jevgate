"""The Jev Decisions API client -- the ONE place in the codebase that talks
to https://openrouter.ai/api/alpha/decisions (an alpha endpoint, isolated
behind this interface per the working rules). No FastAPI import: this module
takes plain values in its constructor, not the app's Settings object, so the
governor library stays usable standalone (L1-01).

Failure policy (and the documented OpenRouter error
matrix):
  - 429/500/502/503/524/529 and network timeouts: retried with exponential
    backoff and jitter.
  - 400/401/403/404: never retried -- a bug or a config error, not a fluke.
  - 402 insufficient credits: never retried, raised distinctly so the caller
    can stop evaluating entirely (governor status evaluation_unavailable).
  - Payload too large: never retried (a truncated payload doesn't grow
    smaller by trying again) -- flagged so the caller can truncate-and-retry
    or set the candidate aside as needs_review. The documented status is 413,
    but a live spike run (scripts/jev_spike.py) against the real endpoint
    got HTTP 400 with {"detail": {"error_type": "max_tokens_exceeded"}}
    instead; both are handled identically.
  - Malformed responses: treated as a failed call, never as a low score.
  - Retries exhausted on an otherwise-retryable failure: status "unscored".
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from governor.contracts import Candidate
from governor.jev.fixtures import JevFixtureStore
from governor.jev.questions import QUESTION_SET_VERSION, questions_wire

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 524, 529}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


class JevStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"  # non-retryable failure: malformed body, 4xx bug/config
    UNSCORED = "unscored"  # retries exhausted on an otherwise-transient failure


class JevError(RuntimeError):
    pass


class JevInsufficientCreditsError(JevError):
    """HTTP 402 -- caller should stop evaluating entirely, not just this call."""


@dataclass
class JevJudgmentResult:
    candidate_id: str
    scores: dict[str, float] | None
    model_version: str | None
    generation_id: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost: float | None
    latency_ms: float
    attempt_count: int
    status: JevStatus
    error: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = field(default=None)
    payload_too_large: bool = False


def _build_state(query: str, candidate: Candidate) -> dict:
    return {
        "query": query,
        "passage": {
            "id": candidate.id,
            "title": candidate.title,
            "text": candidate.text,
            "source_type": candidate.source_type,
        },
    }


class JevClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        api_key: str,
        model_id: str,
        concurrency: int = 8,
        per_call_timeout_s: float = 15.0,
        retry_count: int = 3,
        replay_mode: bool = False,
        fixture_store: JevFixtureStore | None = None,
    ) -> None:
        self._http = http_client
        self._api_key = api_key
        self._model_id = model_id
        self._semaphore = asyncio.Semaphore(concurrency)
        self._per_call_timeout_s = per_call_timeout_s
        self._retry_count = max(retry_count, 1)
        self._replay_mode = replay_mode
        self._fixture_store = fixture_store

    async def judge_many(
        self, query: str, candidates: list[Candidate], *, session_id: str | None = None
    ) -> list[JevJudgmentResult]:
        async def _bounded(candidate: Candidate) -> JevJudgmentResult:
            async with self._semaphore:
                return await self.judge_candidate(query, candidate, session_id=session_id)

        return list(await asyncio.gather(*(_bounded(c) for c in candidates)))

    async def judge_candidate(
        self, query: str, candidate: Candidate, *, session_id: str | None = None
    ) -> JevJudgmentResult:
        payload: dict[str, Any] = {
            "model": self._model_id,
            "state": _build_state(query, candidate),
            "questions": questions_wire(),
        }
        if session_id:
            payload["session_id"] = session_id

        attempt = 0
        last_error = "unknown error"
        start = time.monotonic()

        while attempt < self._retry_count:
            attempt += 1
            try:
                status_code, body = await self._send(payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"transport error: {exc}"
                await self._backoff(attempt)
                continue

            if status_code == 402:
                # Insufficient credits stops the whole evaluation, not just one
                # candidate: propagate past the per-candidate boundary so the
                # caller (governor/P5) can abort the batch as evaluation_unavailable.
                raise JevInsufficientCreditsError(_error_message(body))
            if status_code == 413 or _is_max_tokens_exceeded(status_code, body):
                # A truncated payload doesn't grow smaller by retrying, and this
                # is a per-candidate problem, not a whole-batch one: return a
                # result (flagged payload_too_large) instead of raising.
                # Empirically (spike run against the live endpoint) an oversized
                # payload comes back as HTTP 400 with
                # {"detail": {"error_type": "max_tokens_exceeded"}}, not the
                # documented 413 -- both are treated as payload_too_large.
                result = self._result(
                    candidate,
                    payload,
                    body,
                    status=JevStatus.FAILED,
                    error=f"HTTP {status_code}: {_error_message(body)}",
                    attempt=attempt,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                result.payload_too_large = True
                return result
            if status_code in _NON_RETRYABLE_STATUS_CODES:
                return self._result(
                    candidate,
                    payload,
                    body,
                    status=JevStatus.FAILED,
                    error=f"HTTP {status_code}: {_error_message(body)}",
                    attempt=attempt,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
            if status_code in _RETRYABLE_STATUS_CODES:
                last_error = f"HTTP {status_code}: {_error_message(body)}"
                await self._backoff(attempt)
                continue
            if status_code != 200:
                return self._result(
                    candidate,
                    payload,
                    body,
                    status=JevStatus.FAILED,
                    error=f"unexpected HTTP {status_code}: {_error_message(body)}",
                    attempt=attempt,
                    latency_ms=(time.monotonic() - start) * 1000,
                )

            parsed = _parse_success(body)
            if parsed is None:
                return self._result(
                    candidate,
                    payload,
                    body,
                    status=JevStatus.FAILED,
                    error="malformed response body",
                    attempt=attempt,
                    latency_ms=(time.monotonic() - start) * 1000,
                )

            scores, model_version, generation_id, tokens_in, tokens_out, cost = parsed
            return JevJudgmentResult(
                candidate_id=candidate.id,
                scores=scores,
                model_version=model_version,
                generation_id=generation_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
                latency_ms=(time.monotonic() - start) * 1000,
                attempt_count=attempt,
                status=JevStatus.OK,
                error=None,
                request_payload=payload,
                response_payload=body,
            )

        return self._result(
            candidate,
            payload,
            None,
            status=JevStatus.UNSCORED,
            error=f"retries exhausted: {last_error}",
            attempt=attempt,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    def _result(
        self,
        candidate: Candidate,
        payload: dict,
        body: dict | None,
        *,
        status: JevStatus,
        error: str,
        attempt: int,
        latency_ms: float,
    ) -> JevJudgmentResult:
        return JevJudgmentResult(
            candidate_id=candidate.id,
            scores=None,
            model_version=None,
            generation_id=None,
            tokens_in=None,
            tokens_out=None,
            cost=None,
            latency_ms=latency_ms,
            attempt_count=attempt,
            status=status,
            error=error,
            request_payload=payload,
            response_payload=body,
        )

    async def _backoff(self, attempt: int) -> None:
        if attempt >= self._retry_count:
            return
        delay = min(2**attempt, 8) * (0.5 + random.random())
        await asyncio.sleep(delay)

    async def _send(self, payload: dict) -> tuple[int, dict | None]:
        if self._replay_mode:
            return self._send_replay(payload)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = await self._http.post(
            DECISIONS_URL, json=payload, headers=headers, timeout=self._per_call_timeout_s
        )
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body

    def _send_replay(self, payload: dict) -> tuple[int, dict | None]:
        if self._fixture_store is None:
            raise JevError("replay mode is on but no fixture store was configured")
        fixture = self._fixture_store.get(payload)
        if fixture is None:
            raise JevError("no recorded fixture matches this request")
        if fixture.raise_timeout:
            raise httpx.TimeoutException("simulated timeout from fixture")
        return fixture.status_code, fixture.response_body


def _is_max_tokens_exceeded(status_code: int, body: dict | None) -> bool:
    if status_code != 400 or not body:
        return False
    detail = body.get("detail")
    if isinstance(detail, dict) and detail.get("error_type") == "max_tokens_exceeded":
        return True
    return False


def _error_message(body: dict | None) -> str:
    if not body:
        return "(no body)"
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(body)[:300]


def _parse_success(
    body: dict | None,
) -> tuple[dict[str, float], str, str, int | None, int | None, float | None] | None:
    if not body:
        return None
    try:
        answers = body["answers"]
        scores = {key: float(answer["noul"]) for key, answer in answers.items()}
        model_version = body.get("model", "")
        generation_id = body.get("id", "")
        usage = body.get("usage") or {}
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")
        cost = usage.get("cost")
    except (KeyError, TypeError, ValueError):
        return None
    if set(scores) != set(questions_wire()):
        return None
    return scores, model_version, generation_id, tokens_in, tokens_out, cost


__all__ = [
    "QUESTION_SET_VERSION",
    "JevClient",
    "JevError",
    "JevInsufficientCreditsError",
    "JevJudgmentResult",
    "JevStatus",
]
