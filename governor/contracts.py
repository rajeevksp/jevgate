"""Input and output contracts for the Evidence Governor.

This module carries no FastAPI import, ever -- the governor library must be
importable and usable outside this app (L1-01, L1-11).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    id: str
    text: str
    original_rank: int
    source_location: str | None = None  # e.g. "document.pdf p.3-4"; caller-defined
    title: str | None = None
    source_type: str | None = None
    retrieval_score: float | None = None
    document_type: str | None = None
    authority: str | None = None
    timestamp: str | None = None


class GovernorRequest(BaseModel):
    query: str
    task_description: str | None = None
    recent_turns: list[str] = Field(default_factory=list)
    candidates: list[Candidate]
    # None means "no scope restriction" (e.g. a plain list of texts from a
    # caller with no authorization model); an empty set means nothing is
    # authorized.
    authorized_ids: set[str] | None = None
    token_budget: int
    candidate_limit: int | None = 20
    timeout_ms: int | None = 8000
    policy_version: str | None = None
    allow_external_transmission: bool = False

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "How does the Evidence Governor decide which passages to include?",
                    "candidates": [
                        {
                            "id": "cand-relevant",
                            "title": "Evidence Governor overview",
                            "source_type": "documentation",
                            "original_rank": 1,
                            "text": (
                                "The Evidence Governor sends one OpenRouter Decisions request "
                                "per authorized passage, asking Jev four typed questions about "
                                "the query-passage pair, then routes each passage with "
                                "versioned threshold rules held in application code."
                            ),
                        },
                        {
                            "id": "cand-off-topic",
                            "title": "Bread baking tips",
                            "source_type": "documentation",
                            "original_rank": 2,
                            "text": (
                                "Sourdough bread rises best when the starter is fed twice a "
                                "day at room temperature."
                            ),
                        },
                    ],
                    "token_budget": 2000,
                    "allow_external_transmission": True,
                }
            ]
        }
    }
