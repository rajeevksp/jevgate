# JevGate — Evidence Governance for RAG

**Retrieve broadly. Evaluate evidence. Generate from a governed context.**

[![ci](https://github.com/rajeevksp/jevgate/actions/workflows/ci.yml/badge.svg)](https://github.com/rajeevksp/jevgate/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)

JevGate is a small Python library that sits between **your existing retriever** and **your answering
LLM**. It takes the retrieved candidate passages, asks the
[Jev](https://openrouter.ai/typesafe/jev-1.13) structured decision model (through OpenRouter's
Decisions API) four typed questions about each query–passage pair, applies deterministic, versioned
policy rules that live in your code, and returns a token-budgeted **evidence bundle** with provenance,
exclusions and a decision trace. Project page: <https://rajeevksp.github.io/jevgate/>.

> The project, Python package, import name and CLI are all `jevgate` (`from jevgate.evaluate import evaluate`).
> It is not on PyPI yet; install from GitHub. Earlier drafts used `evidence-governor` / `governor`.

## How it works

```
retriever -> validate -> Jev (4 questions per passage, concurrent) -> policy routing
          -> rerank + near-duplicate removal -> token budget -> EvidenceBundle
```

1. **Receive** candidate passages from any retriever (a plain list of texts is enough).
2. **Judge (model).** For each eligible passage Jev returns four 0–1 scores: `is_relevant`,
   `contains_answer_evidence`, `contradicts_query_premise`, `contains_prompt_injection`.
3. **Route (code).** A named, versioned policy of thresholds (`DEFAULT_POLICY`) decides, first rule
   wins: injection > 0.70 → withhold; contradiction > 0.70 → conflicting; relevance < 0.45 → exclude;
   evidence > 0.55 → accept; otherwise exclude. The thresholds are starting points taken from a
   cookbook, not tuned or validated defaults. Calibrate them on your own labelled data.
4. **Assemble (code).** Order accepted passages by answer evidence, then relevance, then original rank;
   drop near-duplicates (`difflib` similarity ≥ 0.90); fill the token budget greedily (`cl100k_base`),
   reserving a share for conflicting passages.
5. **Trace.** The bundle keeps accepted and conflicting evidence, every exclusion with the rule that
   fired, items needing review, per-passage scores, and usage and latency.

The scores are model judgments and can vary between runs and between model versions. The routing,
ordering, de-duplication and budgeting are ordinary deterministic Python: the same scores and policy
always produce the same bundle. That determinism does not extend to the scores themselves.

What this gives you:

- Works with your existing retriever and generator. No vector database, web framework or server.
  Runtime dependencies are `pydantic`, `httpx` and `tiktoken`.
- Explicit, inspectable routing. Policies are plain code; each exclusion records the rule that fired.
- Replayable policy experiments. `reroute()` rebuilds a bundle from stored judgments under a different
  policy with no new Jev calls (see [Replay and re-routing](#replay-and-re-routing)).
- Recorded-response replay for tests and demos, with no API key and no network.
- 64 tests, including failure paths (timeouts, 429, 5xx, malformed bodies, 402), a runnable example
  and raw benchmark data in [`results/`](results/).

## Initial benchmark

An initial evaluation, not a general result: 101 questions over seven public-document knowledge bases,
one run per question, two answering models. Baseline fills a 3,000-token evidence budget with the
top-ranked chunks of the same top-20 retrieval; governed uses JevGate. Percentages are
`governed / baseline − 1` on totals over the 101 questions.

| Generator | Evidence tokens / query | Generator input tokens | Generator cost | Total cost incl. Jev | Correctness (sum, max 202) | Mean latency |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Haiku 4.5 | 2,879 → 1,364 (**−53%**) | −44% | −36% | **−18%** | 165 → 170 | 5.1 s → 6.6 s (+30%) |
| Gemini | 2,876 → 1,344 (**−53%**) | −42% | −28% | **−12%** | 145 → 143 | 8.7 s → 10.0 s (+15%) |

- *Evidence tokens* are the tokens of the evidence block in the prompt. *Generator input tokens* are
  what the answering model reported and also include the question and instructions, so the two are
  not the same measure. *Total cost* is generator cost plus the Jev fee (about $0.0009 per query for
  20 scored chunks).
- Correctness is graded 0–2 per question by one judge model. The differences (+5 and −2 points out of
  202) are inconclusive: sign test p = 1.0 (Haiku) and p = 0.71 (Gemini).
- The token and cost reductions are measured against a 3,000-token budget baseline, not against sending
  all 20 retrieved chunks (about 8,000 tokens).
- Latency here is the per-request time recorded by the benchmark app; it is not broken down into Jev
  and generation time. A third set of runs in the same folder, with a different generator, showed
  governed latency lower rather than higher, so treat the latency effect as unsettled.
- One run per question, a 0–2 rubric, a single judge, and no independent dataset. The benchmark app
  that produced the runs is not in this repository, and the exact Jev snapshot and Gemini version are
  not recorded. Prompt-injection withholding and conflict flagging were not what this benchmark measured.

Methodology, definitions and raw data: [`results/README.md`](results/README.md),
[`SHOWCASE.md`](SHOWCASE.md). Recompute every figure with `python results/summarize.py`.

## When to use JevGate

It may be worth trying when:

- your generator's input tokens are a meaningful part of your bill (the break-even in this benchmark was
  an input price of roughly $0.58 per 1M tokens; below that the Jev fee exceeded the savings);
- you need to see why each passage was kept, excluded or flagged, and keep that record;
- your corpus contains conflicting or near-duplicate sources and you want them handled explicitly;
- you want hard control of the evidence token budget and cheap, replayable policy experiments.

Trade-offs to weigh first:

- **Latency.** Scoring runs before generation. Mean latency rose 15–30% in the Haiku and Gemini runs.
- **Cost per passage.** Every candidate is one Jev request. Cost grows with the number of candidates
  scored, not with prompt size. Cheap generators may not recoup it.
- **External dependency.** Live evaluation needs OpenRouter and the Jev model, through an endpoint that
  is currently an alpha API.
- **Lost evidence.** A wrong judgment can drop a passage the answer needed. In the Haiku run the
  governed answers scored lower on average on conflicting-source and false-premise questions.

Not every RAG workload will benefit economically. Measure on your own data.

## Install

JevGate is not published on PyPI. Install from GitHub or a checkout:

```bash
pip install git+https://github.com/rajeevksp/jevgate.git
# or from a checkout
pip install -e .
```

Requires Python 3.11+ (CI runs 3.11 and 3.12). You need an OpenRouter API key with access to the Jev
model for live calls.

## Quick start

```python
import asyncio
import httpx

from jevgate.contracts import Candidate, GovernorRequest
from jevgate.evaluate import EvaluationConfig, evaluate
from jevgate.jev.client import JevClient
from jevgate.policy import DEFAULT_POLICY


async def main() -> None:
    request = GovernorRequest(
        query="What does JevGate do?",
        candidates=[
            Candidate(id="c1", text="The governor routes passages using Jev judgments.", original_rank=1),
            Candidate(id="c2", text="Sourdough starters need feeding twice a day.", original_rank=2),
        ],
        token_budget=2000,
        # Opt-in: the query and passage text are sent to OpenRouter. Without it, evaluate()
        # makes no call and returns status "evaluation_unavailable".
        allow_external_transmission=True,
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
    for item in bundle.accepted_evidence:    # feed these (and conflicting_evidence) to your generator
        print(item.id, item.text)
    for item in bundle.excluded_candidates:  # why each passage was dropped
        print(item.id, item.rule_fired)
    for item in bundle.needs_review:         # passages that were NOT scored or were truncated
        print(item.id, item.reason)


asyncio.run(main())
```

A runnable, **free** version replays a recorded Jev response (no API key, no network). Run it from the
repository root, because it reads `tests/fixtures/jev/`:

```bash
python examples/plain_text_retriever.py                                   # replay
OPENROUTER_API_KEY=sk-... python examples/plain_text_retriever.py --live   # real call
```

`model_id="typesafe/jev-1.13"` is a model alias. Responses in the recorded fixtures show it resolving to
a dated snapshot, so pin and record the version you evaluate against if reproducibility matters.

## Replay and re-routing

`reroute(request, stored_judgments, policy, config)` re-derives routing, ranking and budget from
previously obtained judgments under another policy, with no Jev calls. `evaluate()` does not return the
raw judgments, so keep them yourself by calling `JevClient.judge_many()` and storing the results:

```python
from jevgate.evaluate import reroute
from jevgate.policy import PERMISSIVE_POLICY

judgments = {j.candidate_id: j for j in await jev.judge_many(request.query, request.candidates)}
bundle = reroute(request, judgments, PERMISSIVE_POLICY, config)  # no further model calls
```

The library does not persist judgments for you. `PERMISSIVE_POLICY` only demonstrates the mechanism;
it is not a validated alternative.

## Limitations, security and privacy

This describes what the code does today. It is not a security or compliance guarantee.

**Model limitations**

- Jev's judgments can be wrong. A high relevance or answer-evidence score does not mean a passage is
  factually correct; it means the model judged it relevant or answer-bearing.
- Contradiction detection can miss conflicts and can flag passages that do not conflict.
- `contains_prompt_injection` is a risk signal, not a security boundary. Do not rely on it alone to stop
  prompt injection. Keep your own defences in the generator prompt and downstream.
- Filtering can discard useful evidence, and the default thresholds are not calibrated for your data.

**Data transmission**

- Live evaluation sends, for every eligible passage, the query and the passage `id`, `title`, `text` and
  `source_type` to `https://openrouter.ai/api/alpha/decisions`. Passage text longer than
  `max_passage_chars` is truncated before sending (or the passage is set aside if truncation is off).
- `allow_external_transmission=True` is an explicit opt-in that `evaluate()` checks before any call.
  It is a code-level gate, not a statement about regulatory compliance. What OpenRouter or the model
  provider logs or retains is outside this library; check their terms.
- Recorded-response replay (`replay_mode=True` with a fixture store) reads local JSON fixtures matched by an
  exact hash of the request and makes no network call. `evaluate()` still requires the opt-in flag to be
  `True` in replay. `reroute()` never calls Jev.
- `recent_turns`, `task_description` and other `GovernorRequest` fields are not sent to Jev.

**Failure handling**

- Timeouts, network errors and HTTP 429/500/502/503/524/529 are retried with exponential backoff and
  jitter (default 3 attempts, 15 s per call). 400/401/403/404 and malformed responses are not retried.
- A passage that could not be scored (retries exhausted, a non-retryable error, a malformed response, or
  an oversized payload) is never treated as accepted evidence. It is listed in `bundle.needs_review`, and
  the bundle status becomes `partial` if other evidence exists. Your application decides what to do with
  those passages.
- HTTP 402 (insufficient credits) stops the whole batch: the status is `evaluation_unavailable` and
  every candidate is listed as unevaluated.
- Limits: there is no overall deadline across candidates (`GovernorRequest.timeout_ms` and
  `candidate_limit` are declared but not enforced by the library, so limit the candidate list yourself),
  and in replay mode a request with no matching fixture raises `JevError`.

**Output guarantees**

- The bundle and decision trace make selection auditable: you can see the scores, the rule that fired and
  the policy version for each passage. They do not guarantee a correct final answer, and the generator can
  still err on well-chosen evidence.
- Deterministic policy execution does not make the upstream model judgments deterministic.

## Modules and CLI

| Module | Purpose |
| --- | --- |
| `jevgate.contracts` | Input: `Candidate`, `GovernorRequest` |
| `jevgate.bundle` | Output: `EvidenceBundle` and everything inside it |
| `jevgate.validation` | Duplicate/missing ids, empty or over-length text, authorization scope |
| `jevgate.jev.client` | The only place that calls OpenRouter, with retries and record/replay |
| `jevgate.jev.questions` | The four typed questions, versioned |
| `jevgate.policy` | Named, versioned routing thresholds (`DEFAULT_POLICY`) |
| `jevgate.rerank` | Ordering and near-duplicate removal |
| `jevgate.budget` | Token-budget assembly with a share reserved for conflicting evidence |
| `jevgate.evaluate` | `evaluate()` (calls Jev) and `reroute()` (no new calls) |
| `jevgate.cli` | The `jevgate` command |

```bash
export OPENROUTER_API_KEY=sk-...
jevgate evaluate --input request.json --output bundle.json
jevgate policies
```

Environment variables: `OPENROUTER_API_KEY`, `JEV_MODEL_ID`, `JEV_CONCURRENCY`,
`JEV_PER_CALL_TIMEOUT_S`, `JEV_RETRY_COUNT`, `JEV_REPLAY_MODE`, `JEV_FIXTURE_PATH` (default
`tests/fixtures/jev`, relative to the working directory), `MAX_PASSAGE_CHARS`, `ALLOW_TEXT_TRUNCATION`,
`CONFLICT_BUDGET_SHARE`, `DEDUP_SIMILARITY_THRESHOLD`, `BUDGET_TOKENIZER_NAME`.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

No test makes a live call. `tests/fixtures/jev/` holds four request/response pairs recorded from the
live Decisions API; failure paths use `httpx.MockTransport`.

## Benchmark data

Raw per-question data for both generators is in [`results/`](results/), with a column guide, metric
definitions and known caveats in [`results/README.md`](results/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Release notes are in
[CHANGELOG.md](CHANGELOG.md). Licensed under [Apache-2.0](LICENSE).
