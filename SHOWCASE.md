# Evidence Governor: test findings

Jev scores every retrieved passage before your LLM sees it. Across 101 questions, 7 knowledge bases and 2 answer models (Claude Haiku 4.5 and Gemini), the governed prompt carried **53% fewer evidence tokens**. Answer quality was statistically level with the baseline, and generator cost fell, but latency rose.

All numbers are computed from `results/*.csv` and `results/*.json`. Library facts are checked against `governor/`.

## Headline results

| Measure | Baseline | Governed | Change |
| --- | --- | --- | --- |
| Evidence tokens per query | 2,879 | 1,367 | **−53%** |
| Generator tokens per query, Haiku | 3,964 | 2,200 | −44% |
| Generator tokens per query, Gemini | 4,415 | 2,573 | −42% |
| Generator cost per 101 queries, Haiku | $0.503 | $0.324 | −36% |
| Generator cost per 101 queries, Gemini | $0.563 | $0.406 | −28% |
| Net cost including Jev fee, Haiku | $0.503 | $0.412 | −18% |
| Net cost including Jev fee, Gemini | $0.563 | $0.494 | −12% |
| Mean correctness (0–2), Haiku | 1.63 | 1.68 | +0.05, not significant |
| Mean correctness (0–2), Gemini | 1.44 | 1.42 | −0.02, not significant |
| Latency, Haiku | 5.1 s | 6.6 s | +30% |
| Latency, Gemini | 8.7 s | 10.0 s | +15% |

## How the test was set up

- Each query retrieved the **top 20 chunks** of about **400 tokens** each (BGE-M3 + ChromaDB, top-k 20).
- **Baseline** filled a 3,000-token evidence budget in retrieval order. That admits about 7 of the 20 chunks and gave 2,879 tokens on average. It is not the cost of sending all 20 chunks, which would be about 8,000 tokens.
- **Governed** sent all 20 chunks to Jev, routed them by policy, reranked and budgeted the result. Mean evidence was 1,367 tokens.
- Jev made **one request per chunk, 20 per query**, in all 101 runs, asking four typed questions each. That is about 22,500 Jev tokens and **$0.000872 per query** (about $0.039 per 1M Jev tokens).
- Answers were graded 0 to 2 for correctness and grounding by a single judge model, one run per question.

Topics: Cybersecurity IR (18 questions), Procurement (18), Indian Law (18), Climate Migration (17), Quantum (15), Psychology (10), Corporate Reports (5). Question types: ordinary (21), exact-identifier (18), near-miss (15), unanswerable (14), synthesis (12), false-premise (11), conflicting-sources (10).

## How a query travels

1. **Retrieve.** Your retriever returns candidates with an `original_rank`.
2. **Validate**, before any Jev call: missing or duplicate id, empty text, over-length text, out-of-scope id. Rejected candidates cost nothing.
3. **Jev judges.** One Decisions request per eligible passage returns four 0–1 scores: `is_relevant`, `contains_answer_evidence`, `contradicts_query_premise`, `contains_prompt_injection`.
4. **Route** (`DEFAULT_POLICY`), first rule that fires wins: injection > 0.70 → withhold; contradiction > 0.70 → conflict; relevance < 0.45 → exclude; evidence > 0.55 → accept; otherwise exclude.
5. **Rerank, dedupe, budget:** order accepted passages by answer evidence, then relevance, then original rank; drop near-duplicates (similarity ≥ 0.90); fill `token_budget` greedily with `cl100k_base` counts, reserving a share for the conflicting block.
6. **Final context:** `accepted_evidence` and `conflicting_evidence` with text, scores and ranks intact.

Thresholds live in application code, so `reroute()` can re-run routing under another policy from stored judgments with zero new Jev calls.

## Answer quality: parity, not a win

| Model | Mean correctness | Higher | Lower | Unchanged | Sign test p | Holistic grade: governed / baseline / tie |
| --- | --- | --- | --- | --- | --- | --- |
| Haiku | 1.63 → 1.68 | 8 | 7 | 86 | 1.0 | 10 / 15 / 76 |
| Gemini | 1.44 → 1.42 | 13 | 16 | 72 | 0.71 | 17 / 21 / 63 |

Neither difference is distinguishable from noise, and the two grading views disagree in direction for Haiku. Haiku's mean rose because its 8 improved questions gained 12 points in total while its 7 worse questions lost 7. That is a net of 5 points across 101 questions. The separate holistic grade, which picks a better answer per question, favoured the baseline 15 to 10. Both views are consistent with a tie.

Where the Haiku differences sit:

- Correctness gains came from ordinary (+4 points in total) and synthesis (+2) questions.
- They were offset by conflicting-source (−2) and false-premise (−1) questions.
- The holistic grade's 15 baseline wins include 5 false-premise and 3 conflicting-source questions. Dropping a chunk can lose a detail a multi-source answer needs.
- Unanswerable questions scored 2.0 in both modes. The governor cut their evidence by 87% (2,858 → 360 tokens) at no quality cost, but it did not add correctness there either. It did not win points by avoiding hallucinations.

Each category holds only 10 to 21 questions, so treat category gaps as hints.

## What the governor costs

- **Latency** rose 15–30% because scoring runs before generation.
- **Haiku conflicting-source** correctness fell from 1.5 to 1.3; decoy answers rose from 2 to 4 of 101; there were 2 over-refusals.
- **Haiku grounding** score totalled 190 governed against 201 baseline (max 202), a small drop.
- **Gemini** hit its output cap in 41 baseline and 40 governed answers, which depresses scores in both modes.
- **Output tokens are not reduced in general.** Answer length barely moved: −3% in characters overall, −1% outside unanswerable questions, −22% on unanswerable ones, where the governor leaves little to answer from. The "−44% generator tokens" figure comes from the smaller evidence block (input), not from shorter answers. Savings from shorter answers should not be assumed.

## Illustrative savings

Per query, input savings are `2,879 × 52.5% × price per token`, and the Jev fee is about `$0.000872` (20 chunks at about `$0.0000436`). Break-even is an input price of about **$0.58 per 1M tokens**. Prices are example list prices; check current ones.

| Generator | Input $/M | Net per 1,000 queries | Net per month at 10,000 queries/day |
| --- | --- | --- | --- |
| GPT-4o mini | 0.15 | −$0.65 | −$194 |
| Gemini 2.5 Flash | 0.30 | −$0.42 | −$126 |
| Claude Haiku 4.5 | 1.00 | +$0.64 | +$192 |
| Gemini 2.5 Pro | 1.25 | +$1.02 | +$305 |
| GPT-4o | 2.50 | +$2.91 | +$872 |
| Claude Sonnet 4.5 | 3.00 | +$3.66 | +$1,099 |
| Claude Opus 4.5 | 5.00 | +$6.69 | +$2,007 |

**Guidance.** The governor saves money on mid-to-high-priced generators (GPT-4o, Sonnet, Opus class) and only a little on Haiku-priced ones (about $0.64 per 1,000 queries). On models priced below about $0.58 per 1M input tokens (GPT-4o mini, Gemini Flash class) it costs more than it saves. The tests did not measure a quality gain that would justify that, and the policy's prompt-injection withholding and conflict flagging were not tested by this benchmark, so no safety benefit is claimed here.

To lower the fee, score fewer chunks (`candidate_limit`, default 20).

## Plugging it in

The `evidence-governor` package is a library and CLI. It depends only on `pydantic`, `httpx` and `tiktoken`, and never imports FastAPI. It is not published to PyPI yet. You need an OpenRouter API key with access to the Jev model.

```bash
pip install git+https://github.com/rajeevksp/jevgate.git
# or, from a checkout of this repo
pip install -e .
```

```python
import asyncio

import httpx

from governor.contracts import Candidate, GovernorRequest
from governor.evaluate import EvaluationConfig, evaluate
from governor.jev.client import JevClient
from governor.policy import DEFAULT_POLICY

OPENROUTER_API_KEY = "sk-or-..."  # your key
question = "What does the Evidence Governor do?"
hits = [  # whatever your retriever returns, best first
    "The governor routes passages using Jev judgments.",
    "Sourdough starters need feeding twice a day.",
]

request = GovernorRequest(
    query=question,
    candidates=[Candidate(id=f"c{i}", text=t, original_rank=i) for i, t in enumerate(hits, 1)],
    token_budget=2000,
    allow_external_transmission=True,  # required: passages are sent to OpenRouter
)
config = EvaluationConfig(
    max_passage_chars=24000,
    allow_truncation=True,
    conflict_budget_share=0.25,
    dedup_similarity_threshold=0.9,
)


async def run():
    async with httpx.AsyncClient() as http:
        jev = JevClient(http, api_key=OPENROUTER_API_KEY, model_id="typesafe/jev-1.13")
        return await evaluate(request, jev, DEFAULT_POLICY, config)


bundle = asyncio.run(run())

if bundle.status == "insufficient_evidence":
    print("abstain")  # nothing usable: answer "not found" instead of generating
else:
    items = bundle.accepted_evidence + bundle.conflicting_evidence
    context = "\n\n".join(item.text for item in items)
```

Each item carries `id`, `text`, `source_location`, `original_rank`, `final_rank`, `token_count` and `scores`. A CLI is also included: `evidence-governor evaluate --input request.json --output bundle.json`. To try it without an API key, run `python examples/plain_text_retriever.py`, which replays a recorded Jev response.

### What is not in this package

The benchmark traces came from a separate **reference chatbot app** (PDF upload, BGE-M3 embeddings, ChromaDB, a FastAPI JSON API, trace pages, analytics and a shadow mode) that lives outside this repository. It is not part of, or installed by, `pip install evidence-governor`. This package has no server, no HTTP API and no UI.

## Limits of these tests

One run per question, one judge model, 101 questions over seven knowledge bases. Token and cost reductions are large and consistent. Quality differences are not distinguishable from noise. Savings are measured against a 3,000-token baseline budget, not against sending every retrieved chunk.
