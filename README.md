# Evidence Governor

[![ci](https://github.com/rajeevksp/jevgate/actions/workflows/ci.yml/badge.svg)](https://github.com/rajeevksp/jevgate/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

A small library that sits between **any retriever** and **your answering LLM**. For each
query–passage pair it asks the [Jev](https://openrouter.ai/typesafe/jev-1.13) decision model (via
OpenRouter's Decisions API) four typed questions, routes each passage with versioned threshold
rules that live in your code, and returns a compact, ranked, token-budgeted **evidence bundle**
with full provenance and a decision trace.

The four questions: *is it relevant? does it contain answer evidence? does it contradict the
query's premise? does it contain a prompt injection?*

No FastAPI, no database, no vector store required. It works on a plain Python list of texts.

## Why

On a 101-question RAG benchmark over seven public-document knowledge bases (see
[`results/`](results/) and [`SHOWCASE.md`](SHOWCASE.md)), replacing "fill a 3,000-token budget with
the top-ranked chunks" with the governor gave:

| Generator | Evidence tokens | Generator input tokens | Generator cost | Total cost incl. Jev | Answer correctness (0–2 × 101) |
| --- | --- | --- | --- | --- | --- |
| Claude Haiku 4.5 | **−53%** | −44% | −36% | **−18%** | 165 → 170 |
| Gemini | **−53%** | −42% | −28% | **−12%** | 145 → 143 |

The governor removes off-topic, duplicate, contradicting and injected passages before the
generator sees them, so you pay for fewer tokens at about the same answer quality. The trade-off is
latency: one extra parallel Jev round-trip per query (mean 5.1 s → 6.6 s on Haiku).

Caveats: 101 queries, one run each, answers graded on a 0–2 rubric (see
[`results/README.md`](results/README.md)). Treat correctness differences as noise and the token and
cost reductions as the measured effect. Run it on your own data before relying on it.

## Install

```bash
pip install git+https://github.com/rajeevksp/jevgate.git
# or from a checkout
pip install -e .
```

Requires Python 3.11+. Dependencies: `pydantic`, `httpx`, `tiktoken`.

## Quick start

```python
import asyncio
import httpx

from governor.contracts import Candidate, GovernorRequest
from governor.evaluate import EvaluationConfig, evaluate
from governor.jev.client import JevClient
from governor.policy import DEFAULT_POLICY


async def main() -> None:
    request = GovernorRequest(
        query="What does the Evidence Governor do?",
        candidates=[
            Candidate(id="c1", text="The governor routes passages using Jev judgments.", original_rank=1),
            Candidate(id="c2", text="Sourdough starters need feeding twice a day.", original_rank=2),
        ],
        token_budget=2000,
        allow_external_transmission=True,  # required: passages are sent to OpenRouter
    )
    config = EvaluationConfig(
        max_passage_chars=24000,
        allow_truncation=True,
        conflict_budget_share=0.25,
        dedup_similarity_threshold=0.9,
    )
    async with httpx.AsyncClient() as http:
        jev = JevClient(http, api_key="YOUR_OPENROUTER_API_KEY", model_id="typesafe/jev-1.13")
        bundle = await evaluate(request, jev, DEFAULT_POLICY, config)

    print(bundle.status)
    for item in bundle.accepted_evidence:    # feed these to your generator
        print(item.id, item.text)
    for item in bundle.excluded_candidates:  # why each passage was dropped
        print(item.id, item.rule_fired)


asyncio.run(main())
```

A runnable, **free** version that replays recorded Jev responses (no API key needed):

```bash
python examples/plain_text_retriever.py                                  # replay
OPENROUTER_API_KEY=sk-... python examples/plain_text_retriever.py --live  # real call
```

## How it works

```
retriever -> validate -> Jev (4 questions per passage, parallel) -> policy routing
          -> rerank + dedup -> token budget -> EvidenceBundle
```

| Module | Purpose |
| --- | --- |
| `governor.contracts` | Input: `Candidate`, `GovernorRequest` |
| `governor.bundle` | Output: `EvidenceBundle` and everything inside it |
| `governor.validation` | Duplicate/missing ids, over-length text, authorization scope |
| `governor.jev.client` | The only place that calls OpenRouter, with retries and record/replay |
| `governor.jev.questions` | The four typed questions, versioned |
| `governor.policy` | Named, versioned routing thresholds (`DEFAULT_POLICY`) |
| `governor.rerank` | Ordering and near-duplicate removal |
| `governor.budget` | Token-budget assembly with a share reserved for conflicting evidence |
| `governor.evaluate` | `evaluate()` (calls Jev) and `reroute()` (no new calls) |
| `governor.cli` | The `evidence-governor` command |

Routing thresholds are plain code, not a model decision, so they are auditable and tunable.
`reroute()` re-derives routing, rerank and budget under a different policy from a previous run's
judgments with **zero** new Jev calls, which makes threshold sweeps cheap.

If Jev can't score a passage (timeout, retries exhausted) it is marked unscored, never silently
accepted. Passages are only sent externally when `allow_external_transmission=True`.

## CLI

```bash
export OPENROUTER_API_KEY=sk-...
evidence-governor evaluate --input request.json --output bundle.json
evidence-governor policies
```

Environment variables: `JEV_MODEL_ID`, `JEV_CONCURRENCY`, `JEV_PER_CALL_TIMEOUT_S`,
`JEV_RETRY_COUNT`, `JEV_REPLAY_MODE`, `JEV_FIXTURE_PATH`, `MAX_PASSAGE_CHARS`,
`ALLOW_TEXT_TRUNCATION`, `CONFLICT_BUDGET_SHARE`, `DEDUP_SIMILARITY_THRESHOLD`,
`BUDGET_TOKENIZER_NAME`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

No test makes a live call. `tests/fixtures/jev/` holds four real request/response pairs recorded
from the live Decisions API; failure paths (timeouts, 429, 5xx, malformed bodies, 402) use
`httpx.MockTransport`.

## Benchmark results

Raw per-question data for both generators is in [`results/`](results/), with a column guide in
[`results/README.md`](results/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [Apache-2.0](LICENSE).
