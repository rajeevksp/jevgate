"""Routing policy: a named, versioned set of thresholds.
Tests run in a fixed order, first match wins. The decision to include a
passage never lives in a Jev question's wording -- it lives here, in code,
so a new policy can re-route stored judgments with zero new Jev calls.

Thresholds are starting points from TypeSafe's cookbook, not validated
defaults (confirmed sensible against real Jev output:
an injection passage scored 0.98 on contains_prompt_injection, a genuine
contradiction scored 0.97 on contradicts_query_premise, an off-topic passage
scored under 0.05 on every question).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from governor.jev.questions import QUESTION_SET_VERSION


class Route(StrEnum):
    ACCEPT = "accept"
    CONFLICT = "conflict"
    EXCLUDE = "exclude"
    WITHHOLD = "withhold"


@dataclass(frozen=True)
class PolicyThresholds:
    injection_max: float = 0.70
    contradiction_min: float = 0.70
    relevance_min: float = 0.45
    evidence_min: float = 0.55


@dataclass(frozen=True)
class Policy:
    name: str
    version: str
    thresholds: PolicyThresholds
    question_set_version: str = QUESTION_SET_VERSION

    @property
    def full_name(self) -> str:
        return f"{self.name}-{self.version}"


@dataclass
class RoutingDecision:
    route: Route
    rule_fired: str
    needs_review_overlap: bool = False  # injection AND contradiction both fired


def route_scores(scores: dict[str, float], policy: Policy) -> RoutingDecision:
    t = policy.thresholds
    injection = scores.get("contains_prompt_injection", 0.0)
    contradiction = scores.get("contradicts_query_premise", 0.0)
    relevance = scores.get("is_relevant", 0.0)
    evidence = scores.get("contains_answer_evidence", 0.0)

    if injection > t.injection_max:
        return RoutingDecision(
            Route.WITHHOLD,
            "injection_above_threshold",
            needs_review_overlap=contradiction > t.contradiction_min,
        )
    if contradiction > t.contradiction_min:
        return RoutingDecision(Route.CONFLICT, "contradiction_above_threshold")
    if relevance < t.relevance_min:
        return RoutingDecision(Route.EXCLUDE, "relevance_below_floor")
    if evidence > t.evidence_min:
        return RoutingDecision(Route.ACCEPT, "evidence_above_threshold")
    return RoutingDecision(Route.EXCLUDE, "no_rule_matched")


DEFAULT_POLICY = Policy(name="cookbook-defaults", version="v1", thresholds=PolicyThresholds())

# A second named policy so re-route (spec: "re-route a past run under a
# named policy without new Jev calls") has somewhere meaningful to switch
# to. Not a validated alternative -- real calibration is threshold
# sweep on labelled data; this just demonstrates the mechanism.
PERMISSIVE_POLICY = Policy(
    name="cookbook-permissive", version="v1", thresholds=PolicyThresholds(evidence_min=0.40)
)

POLICIES: dict[str, Policy] = {
    DEFAULT_POLICY.full_name: DEFAULT_POLICY,
    PERMISSIVE_POLICY.full_name: PERMISSIVE_POLICY,
}


def get_policy(name: str) -> Policy:
    try:
        return POLICIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown policy: {name!r}") from exc
