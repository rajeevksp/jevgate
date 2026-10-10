from __future__ import annotations

import pytest

from governor.bundle import BundleStatus
from governor.contracts import Candidate, GovernorRequest
from governor.evaluate import EvaluationConfig, evaluate, reroute
from governor.policy import DEFAULT_POLICY
from tests.fakes import FakeJevClient, ok_judgment, unscored_judgment

CONFIG = EvaluationConfig(
    max_passage_chars=1000,
    allow_truncation=True,
    conflict_budget_share=0.25,
    dedup_similarity_threshold=0.9,
)


def _request(candidates: list[Candidate], **kwargs) -> GovernorRequest:
    defaults = {
        "query": "q",
        "candidates": candidates,
        "token_budget": 1000,
        "allow_external_transmission": True,
    }
    defaults.update(kwargs)
    return GovernorRequest(**defaults)


@pytest.mark.asyncio
async def test_ok_bundle_accepts_and_conflicts_and_excludes_correctly() -> None:
    candidates = [
        Candidate(id="accepted-1", text="Clear answer evidence.", original_rank=1),
        Candidate(id="conflict-1", text="Contradicts the premise.", original_rank=2),
        Candidate(id="excluded-1", text="Off topic entirely.", original_rank=3),
        Candidate(id="withheld-1", text="Contains an injection attempt.", original_rank=4),
    ]
    jev = FakeJevClient(
        {
            "accepted-1": ok_judgment("accepted-1", is_relevant=0.9, contains_answer_evidence=0.9),
            "conflict-1": ok_judgment("conflict-1", is_relevant=0.9, contradicts_query_premise=0.9),
            "excluded-1": ok_judgment("excluded-1", is_relevant=0.1, contains_answer_evidence=0.1),
            "withheld-1": ok_judgment("withheld-1", contains_prompt_injection=0.9),
        }
    )

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert bundle.status == BundleStatus.OK
    assert [e.id for e in bundle.accepted_evidence] == ["accepted-1"]
    assert [e.id for e in bundle.conflicting_evidence] == ["conflict-1"]
    excluded_ids = {e.id for e in bundle.excluded_candidates}
    assert "excluded-1" in excluded_ids
    assert "withheld-1" in excluded_ids
    assert bundle.needs_review == []
    assert bundle.usage_and_latency.jev_requests == 4


@pytest.mark.asyncio
async def test_verbatim_text_and_provenance_are_intact() -> None:
    candidate = Candidate(
        id="c1", text="Exact verbatim text.", original_rank=1, source_location="doc.pdf p.1"
    )
    jev = FakeJevClient({"c1": ok_judgment("c1", is_relevant=0.9, contains_answer_evidence=0.9)})
    candidates = [candidate]

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    item = bundle.accepted_evidence[0]
    assert item.text == "Exact verbatim text."
    assert item.id == "c1"
    assert item.source_location == "doc.pdf p.1"


@pytest.mark.asyncio
async def test_no_score_is_ever_labelled_answer_confidence() -> None:
    bundle_json = (
        await evaluate(
            _request([Candidate(id="c1", text="text", original_rank=1)]),
            FakeJevClient({"c1": ok_judgment("c1", is_relevant=0.9, contains_answer_evidence=0.9)}),
            DEFAULT_POLICY,
            CONFIG,
        )
    ).model_dump_json()
    assert "confidence" not in bundle_json.lower()


@pytest.mark.asyncio
async def test_transmission_disabled_returns_evaluation_unavailable_without_calling_jev() -> None:
    candidates = [Candidate(id="c1", text="text", original_rank=1)]
    jev = FakeJevClient()

    bundle = await evaluate(
        _request(candidates, allow_external_transmission=False), jev, DEFAULT_POLICY, CONFIG
    )

    assert bundle.status == BundleStatus.EVALUATION_UNAVAILABLE
    assert jev.calls == []
    assert [r.id for r in bundle.needs_review] == ["c1"]
    assert bundle.needs_review[0].reason == "unevaluated"


@pytest.mark.asyncio
async def test_no_eligible_candidates_is_insufficient_evidence() -> None:
    candidates = [Candidate(id="c1", text="   ", original_rank=1)]  # empty after strip
    jev = FakeJevClient()

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert bundle.status == BundleStatus.INSUFFICIENT_EVIDENCE
    assert jev.calls == []
    assert any(e.id == "c1" for e in bundle.excluded_candidates)


@pytest.mark.asyncio
async def test_all_excluded_by_policy_is_insufficient_evidence() -> None:
    candidates = [Candidate(id="c1", text="off topic", original_rank=1)]
    jev = FakeJevClient({"c1": ok_judgment("c1", is_relevant=0.1, contains_answer_evidence=0.1)})

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert bundle.status == BundleStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.asyncio
async def test_unscored_judgment_is_partial_and_listed_in_needs_review() -> None:
    candidates = [
        Candidate(id="good", text="Clear answer evidence.", original_rank=1),
        Candidate(id="bad", text="Some text.", original_rank=2),
    ]
    jev = FakeJevClient(
        {
            "good": ok_judgment("good", is_relevant=0.9, contains_answer_evidence=0.9),
            "bad": unscored_judgment("bad"),
        }
    )

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert bundle.status == BundleStatus.PARTIAL
    assert any(r.id == "bad" and r.reason == "unscored" for r in bundle.needs_review)
    assert [e.id for e in bundle.accepted_evidence] == ["good"]


@pytest.mark.asyncio
async def test_truncated_input_is_flagged_partial_text_in_needs_review() -> None:
    long_text = "x" * 2000
    candidates = [Candidate(id="c1", text=long_text, original_rank=1)]
    jev = FakeJevClient({"c1": ok_judgment("c1", is_relevant=0.9, contains_answer_evidence=0.9)})

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert any(r.id == "c1" and r.reason == "truncated" for r in bundle.needs_review)


@pytest.mark.asyncio
async def test_injection_contradiction_overlap_withheld_and_needs_review() -> None:
    candidates = [Candidate(id="c1", text="text", original_rank=1)]
    jev = FakeJevClient(
        {"c1": ok_judgment("c1", contains_prompt_injection=0.9, contradicts_query_premise=0.9)}
    )

    bundle = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)

    assert bundle.accepted_evidence == []
    assert bundle.conflicting_evidence == []
    excluded = bundle.excluded_candidates
    assert any(e.id == "c1" and e.rule_fired == "injection_above_threshold" for e in excluded)
    review = bundle.needs_review
    assert any(r.id == "c1" and r.reason == "injection_contradiction_overlap" for r in review)


@pytest.mark.asyncio
async def test_reroute_uses_zero_new_jev_calls_and_can_change_routes() -> None:
    candidates = [Candidate(id="c1", text="borderline text", original_rank=1)]
    # Scores sit between the default policy's relevance floor and evidence
    # threshold: excluded under the default policy, accepted under a looser one.
    judgment = ok_judgment("c1", is_relevant=0.5, contains_answer_evidence=0.5)
    jev = FakeJevClient({"c1": judgment})

    first = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)
    assert first.status == BundleStatus.INSUFFICIENT_EVIDENCE
    assert jev.calls == [("q", ["c1"], None)]

    from governor.policy import Policy, PolicyThresholds

    looser_policy = Policy(
        name="looser", version="v1", thresholds=PolicyThresholds(evidence_min=0.4)
    )
    second = reroute(_request(candidates), {"c1": judgment}, looser_policy, CONFIG)

    assert jev.calls == [("q", ["c1"], None)]  # still just the one original call
    assert second.status == BundleStatus.OK
    assert [e.id for e in second.accepted_evidence] == ["c1"]


@pytest.mark.asyncio
async def test_reroute_and_evaluate_agree_when_given_the_same_judgments() -> None:
    candidates = [
        Candidate(id="a", text="Answer evidence here.", original_rank=1),
        Candidate(id="b", text="Contradicts the premise.", original_rank=2),
    ]
    judgments = {
        "a": ok_judgment("a", is_relevant=0.9, contains_answer_evidence=0.9),
        "b": ok_judgment("b", is_relevant=0.9, contradicts_query_premise=0.9),
    }
    jev = FakeJevClient(judgments)

    evaluated = await evaluate(_request(candidates), jev, DEFAULT_POLICY, CONFIG)
    rerouted = reroute(_request(candidates), judgments, DEFAULT_POLICY, CONFIG)

    assert evaluated.model_dump(exclude={"usage_and_latency"}) == rerouted.model_dump(
        exclude={"usage_and_latency"}
    )
