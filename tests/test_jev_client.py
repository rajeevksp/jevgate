from __future__ import annotations

import json

import httpx
import pytest

from jevgate.contracts import Candidate
from jevgate.jev.client import JevClient, JevError, JevInsufficientCreditsError, JevStatus
from jevgate.jev.fixtures import JevFixtureStore
from jevgate.jev.questions import questions_wire


def _scores(**overrides: float) -> dict[str, float]:
    scores = dict.fromkeys(questions_wire(), 0.1)
    scores.update(overrides)
    return scores


def _ok_body(scores: dict[str, float] | None = None) -> dict:
    scores = scores or dict.fromkeys(questions_wire(), 0.5)
    return {
        "id": "gen-dec-test",
        "model": "typesafe/jev-1.13-test",
        "provider": "TypeSafe",
        "answers": {k: {"type": "noul", "noul": v} for k, v in scores.items()},
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost": 0.00001},
    }


def _client(handler, *, retry_count: int = 3, no_sleep: bool = True, monkeypatch=None) -> JevClient:
    if no_sleep and monkeypatch is not None:
        import jevgate.jev.client as client_module

        async def _fast_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(client_module.asyncio, "sleep", _fast_sleep)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return JevClient(
        http_client,
        api_key="test-key",
        model_id="typesafe/jev-1.13",
        concurrency=8,
        per_call_timeout_s=5.0,
        retry_count=retry_count,
    )


@pytest.mark.asyncio
async def test_successful_call_returns_scores() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body(_scores(is_relevant=0.9)))

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.OK
    assert result.scores["is_relevant"] == 0.9
    assert result.model_version == "typesafe/jev-1.13-test"
    assert result.generation_id == "gen-dec-test"
    assert result.tokens_in == 100
    assert result.cost == 0.00001
    assert result.attempt_count == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_429_then_success_retries_and_succeeds(monkeypatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}})
        return httpx.Response(200, json=_ok_body())

    client = _client(handler, monkeypatch=monkeypatch)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.OK
    assert result.attempt_count == 2
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_5xx_exhausts_retries_and_is_unscored(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"code": 503, "message": "unavailable"}})

    client = _client(handler, retry_count=3, monkeypatch=monkeypatch)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.UNSCORED
    assert result.attempt_count == 3
    assert result.scores is None
    assert "503" in result.error


@pytest.mark.asyncio
async def test_timeout_is_retried_and_can_still_succeed(monkeypatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out")
        return httpx.Response(200, json=_ok_body())

    client = _client(handler, monkeypatch=monkeypatch)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.OK
    assert result.attempt_count == 2


@pytest.mark.asyncio
async def test_malformed_response_is_a_failure_not_a_low_score() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.FAILED
    assert result.scores is None
    assert "malformed" in result.error


@pytest.mark.asyncio
async def test_non_json_body_is_treated_as_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.FAILED


@pytest.mark.asyncio
async def test_400_bug_is_failed_and_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"code": 400, "message": "bad request"}})

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.FAILED
    assert calls["n"] == 1  # never retried
    assert result.payload_too_large is False


@pytest.mark.asyncio
async def test_max_tokens_exceeded_400_is_flagged_payload_too_large_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"detail": {"error_type": "max_tokens_exceeded"}})

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.status == JevStatus.FAILED
    assert result.payload_too_large is True
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_documented_413_is_also_flagged_payload_too_large() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(413, json={"error": {"code": 413, "message": "too large"}})

    client = _client(handler)
    result = await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))

    assert result.payload_too_large is True
    assert result.status == JevStatus.FAILED


@pytest.mark.asyncio
async def test_402_raises_insufficient_credits_and_is_never_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(402, json={"error": {"code": 402, "message": "insufficient credits"}})

    client = _client(handler)
    with pytest.raises(JevInsufficientCreditsError):
        await client.judge_candidate("q", Candidate(id="c1", text="text", original_rank=1))
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_judge_many_respects_concurrency_and_returns_all_results(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body())

    client = _client(handler, monkeypatch=monkeypatch)
    candidates = [Candidate(id=f"c{i}", text="text", original_rank=i) for i in range(15)]
    results = await client.judge_many("q", candidates)

    assert len(results) == 15
    assert all(r.status == JevStatus.OK for r in results)
    assert {r.candidate_id for r in results} == {c.id for c in candidates}


@pytest.mark.asyncio
async def test_replay_mode_answers_from_a_recorded_fixture(tmp_path) -> None:
    store = JevFixtureStore(tmp_path)
    candidate = Candidate(id="c1", text="some passage text", original_rank=1)
    passage = {"id": "c1", "title": None, "text": "some passage text", "source_type": None}
    payload = {
        "model": "typesafe/jev-1.13",
        "state": {"query": "q", "passage": passage},
        "questions": questions_wire(),
    }
    store.save("case1", payload, 200, _ok_body(_scores(is_relevant=0.77)))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay mode must never make a real HTTP call")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = JevClient(
        http_client,
        api_key="unused",
        model_id="typesafe/jev-1.13",
        replay_mode=True,
        fixture_store=store,
    )

    result = await client.judge_candidate("q", candidate)
    assert result.status == JevStatus.OK
    assert result.scores["is_relevant"] == 0.77


@pytest.mark.asyncio
async def test_replay_mode_raises_when_no_fixture_matches(tmp_path) -> None:
    store = JevFixtureStore(tmp_path)
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    http_client = httpx.AsyncClient(transport=transport)
    client = JevClient(
        http_client,
        api_key="unused",
        model_id="typesafe/jev-1.13",
        replay_mode=True,
        fixture_store=store,
    )

    with pytest.raises(JevError, match="no recorded fixture"):
        await client.judge_candidate("q", Candidate(id="unrecorded", text="x", original_rank=1))


def _replay_client(store: JevFixtureStore) -> JevClient:
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    return JevClient(
        httpx.AsyncClient(transport=transport),
        api_key="unused",
        model_id="typesafe/jev-1.13",
        retry_count=2,
        replay_mode=True,
        fixture_store=store,
    )


@pytest.mark.asyncio
async def test_replayed_5xx_fixture_exhausts_retries_and_is_unscored(tmp_path, monkeypatch) -> None:
    import jevgate.jev.client as client_module

    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _fast_sleep)

    store = JevFixtureStore(tmp_path)
    candidate = Candidate(id="c1", text="text", original_rank=1)
    payload = {
        "model": "typesafe/jev-1.13",
        "state": {
            "query": "q",
            "passage": {"id": "c1", "title": None, "text": "text", "source_type": None},
        },
        "questions": questions_wire(),
    }
    store.save("failure-case", payload, 503, {"error": {"code": 503, "message": "unavailable"}})

    result = await _replay_client(store).judge_candidate("q", candidate)

    assert result.status == JevStatus.UNSCORED
    assert result.attempt_count == 2


@pytest.mark.asyncio
async def test_replayed_timeout_fixture_is_retried(tmp_path, monkeypatch) -> None:
    import jevgate.jev.client as client_module

    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _fast_sleep)

    store = JevFixtureStore(tmp_path)
    candidate = Candidate(id="c1", text="text", original_rank=1)
    payload = {
        "model": "typesafe/jev-1.13",
        "state": {
            "query": "q",
            "passage": {"id": "c1", "title": None, "text": "text", "source_type": None},
        },
        "questions": questions_wire(),
    }
    fixture_path = store.save("timeout-case", payload, 200, None)
    data = json.loads(fixture_path.read_text())
    data["raise_timeout"] = True
    fixture_path.write_text(json.dumps(data))
    fresh_store = JevFixtureStore(tmp_path)  # force a reload with raise_timeout set

    result = await _replay_client(fresh_store).judge_candidate("q", candidate)

    assert result.status == JevStatus.UNSCORED
    assert "timeout" in result.error.lower() or "transport" in result.error.lower()


def test_fixture_store_round_trips(tmp_path) -> None:
    store = JevFixtureStore(tmp_path)
    payload = {"a": 1, "b": {"c": 2}}
    store.save("name", payload, 200, {"ok": True})

    fresh_store = JevFixtureStore(tmp_path)
    fixture = fresh_store.get(payload)
    assert fixture is not None
    assert fixture.status_code == 200
    assert fixture.response_body == {"ok": True}


def test_fixture_files_are_valid_json(tmp_path) -> None:
    # Sanity check on the real recorded fixtures committed to the repo.
    import pathlib

    fixture_dir = pathlib.Path("tests/fixtures/jev")
    files = list(fixture_dir.glob("*.json"))
    assert len(files) >= 4
    for f in files:
        data = json.loads(f.read_text())
        assert "request" in data
        assert "status_code" in data
