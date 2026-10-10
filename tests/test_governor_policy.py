from __future__ import annotations

import pytest

from jevgate.policy import DEFAULT_POLICY, Route, route_scores


def _scores(**overrides: float) -> dict[str, float]:
    base = {
        "is_relevant": 0.5,
        "contains_answer_evidence": 0.5,
        "contradicts_query_premise": 0.1,
        "contains_prompt_injection": 0.1,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("scores", "expected_route", "expected_rule"),
    [
        # Rule 1: injection above threshold wins over everything else.
        (
            _scores(contains_prompt_injection=0.71, is_relevant=0.9, contains_answer_evidence=0.9),
            Route.WITHHOLD,
            "injection_above_threshold",
        ),
        # Rule 2: contradiction above threshold, injection not fired.
        (
            _scores(contradicts_query_premise=0.71, is_relevant=0.9, contains_answer_evidence=0.9),
            Route.CONFLICT,
            "contradiction_above_threshold",
        ),
        # Rule 3: relevance floor.
        (
            _scores(is_relevant=0.44, contains_answer_evidence=0.9),
            Route.EXCLUDE,
            "relevance_below_floor",
        ),
        # Rule 4: accepted.
        (
            _scores(is_relevant=0.5, contains_answer_evidence=0.56),
            Route.ACCEPT,
            "evidence_above_threshold",
        ),
        # Rule 5: falls through everything.
        (
            _scores(is_relevant=0.5, contains_answer_evidence=0.5),
            Route.EXCLUDE,
            "no_rule_matched",
        ),
        # Boundary: exactly at threshold does not fire (strict >).
        (_scores(contains_prompt_injection=0.70), Route.EXCLUDE, "no_rule_matched"),
        (_scores(contradicts_query_premise=0.70), Route.EXCLUDE, "no_rule_matched"),
        (_scores(is_relevant=0.45), Route.EXCLUDE, "no_rule_matched"),
        (_scores(contains_answer_evidence=0.55), Route.EXCLUDE, "no_rule_matched"),
    ],
)
def test_routing_rules_in_order(scores, expected_route, expected_rule) -> None:
    decision = route_scores(scores, DEFAULT_POLICY)
    assert decision.route == expected_route
    assert decision.rule_fired == expected_rule


def test_injection_and_contradiction_overlap_flags_needs_review() -> None:
    scores = _scores(contains_prompt_injection=0.9, contradicts_query_premise=0.9)
    decision = route_scores(scores, DEFAULT_POLICY)
    assert decision.route == Route.WITHHOLD
    assert decision.needs_review_overlap is True


def test_injection_without_contradiction_does_not_flag_overlap() -> None:
    scores = _scores(contains_prompt_injection=0.9, contradicts_query_premise=0.1)
    decision = route_scores(scores, DEFAULT_POLICY)
    assert decision.route == Route.WITHHOLD
    assert decision.needs_review_overlap is False


def test_injection_takes_priority_over_relevance_and_evidence() -> None:
    # Even a highly relevant, evidence-rich passage is withheld if it injects.
    scores = _scores(
        contains_prompt_injection=0.99, is_relevant=0.99, contains_answer_evidence=0.99
    )
    decision = route_scores(scores, DEFAULT_POLICY)
    assert decision.route == Route.WITHHOLD


def test_contradiction_takes_priority_over_relevance_and_evidence() -> None:
    scores = _scores(
        contradicts_query_premise=0.99, is_relevant=0.99, contains_answer_evidence=0.99
    )
    decision = route_scores(scores, DEFAULT_POLICY)
    assert decision.route == Route.CONFLICT
