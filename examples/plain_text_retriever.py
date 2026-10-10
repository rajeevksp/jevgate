"""Sample retriever: the Evidence Governor working from a plain Python list
of texts, no vector store, no database, and no part of this repo's `app`
package (spec section C, L1-01: "The Chroma chatbot and a plain list of
texts both work without a plugin").

Only `governor.*` is imported below -- if this script runs, the governor
truly has no dependency on the reference app or any database migration.

By default this replays one of the real fixtures recorded from the live
Decisions API in Phase 4 (tests/fixtures/jev/relevant.json), so it runs for
free with no OpenRouter key. Set OPENROUTER_API_KEY and pass --live to make
a real call instead.

Usage:
    python examples/plain_text_retriever.py
    OPENROUTER_API_KEY=sk-... python examples/plain_text_retriever.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from governor.contracts import Candidate, GovernorRequest
from governor.evaluate import EvaluationConfig, evaluate
from governor.jev.client import JevClient
from governor.jev.fixtures import JevFixtureStore
from governor.policy import DEFAULT_POLICY

# A plain Python list -- this is the entire "retriever". Any data source
# that can produce (id, title, text) triples works the same way: a grep over
# local files, a search API's results, rows from a spreadsheet, and so on.
# title/source_type here match tests/fixtures/jev/*.json exactly, recorded
# from the live API in Phase 4, so --replay (the default) can answer them.
PLAIN_TEXT_CORPUS: list[Candidate] = [
    Candidate(
        id="cand-relevant",
        title="Evidence Governor overview",
        source_type="documentation",
        original_rank=1,
        text=(
            "The Evidence Governor sends one OpenRouter Decisions request per "
            "authorized passage, asking Jev four typed questions about the "
            "query-passage pair, then routes each passage with versioned "
            "threshold rules held in application code."
        ),
    ),
    Candidate(
        id="cand-off-topic",
        title="Bread baking tips",
        source_type="documentation",
        original_rank=2,
        text=(
            "Sourdough bread rises best when the starter is fed twice a day at room temperature."
        ),
    ),
]

QUERY = "How does the Evidence Governor decide which passages to include?"


async def main(live: bool) -> None:
    request = GovernorRequest(
        query=QUERY,
        candidates=PLAIN_TEXT_CORPUS,
        token_budget=2000,
        allow_external_transmission=True,
    )
    config = EvaluationConfig(
        max_passage_chars=24000,
        allow_truncation=True,
        conflict_budget_share=0.25,
        dedup_similarity_threshold=0.9,
    )

    async with httpx.AsyncClient() as http_client:
        if live:
            jev_client = JevClient(
                http_client,
                api_key=os.environ["OPENROUTER_API_KEY"],
                model_id="typesafe/jev-1.13",
            )
        else:
            fixtures = JevFixtureStore("tests/fixtures/jev")
            jev_client = JevClient(
                http_client,
                api_key="unused-in-replay-mode",
                model_id="typesafe/jev-1.13",
                replay_mode=True,
                fixture_store=fixtures,
            )

        bundle = await evaluate(request, jev_client, DEFAULT_POLICY, config)

    print(f"status: {bundle.status}")
    print(f"accepted evidence ({len(bundle.accepted_evidence)}):")
    for item in bundle.accepted_evidence:
        print(f"  [{item.id}] {item.text[:80]}...")
    print(f"excluded candidates ({len(bundle.excluded_candidates)}):")
    for item in bundle.excluded_candidates:
        print(f"  [{item.id}] rule_fired={item.rule_fired}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make a real OpenRouter call")
    args = parser.parse_args()
    asyncio.run(main(args.live))
