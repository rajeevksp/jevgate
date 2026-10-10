# Benchmark results

101 questions over seven public-document knowledge bases (cybersecurity incident response,
procurement, Indian law, climate migration, quantum computing, psychology, corporate reports) in
seven question types (ordinary, exact-identifier, near-miss, false-premise, conflicting-sources,
unanswerable, synthesis). Each question
was answered twice per generator: **baseline** (top-20 retrieved chunks, plain budget fill) and
**governed** (JevGate, `DEFAULT_POLICY`). Retrieval: BGE-M3 + ChromaDB, top-k 20.

| File | Contents |
| --- | --- |
| `haiku_baseline_vs_governed_graded.csv` | Per-question graded results, Claude Haiku 4.5 generator |
| `gemini_baseline_vs_governed_graded.csv` | Same, Gemini generator |
| `jev_baseline_vs_governed_runs.csv` | Per-question run metadata for a **third, separate set of 101 runs** (see "Run sets" below). Not the Haiku or Gemini results |
| `*_rerun_results.json` | Raw answers and metrics per question and mode |
| `summarize.py` | Recomputes every headline figure from the files above (`python results/summarize.py`) |
| `grade_packet_*.json`, `gemini_grade_packet_*.json` | Question, reference answer, expected evidence and both answers, as used for grading |

## Column guide

`b_` = baseline, `g_` = governed.

| Column | Meaning |
| --- | --- |
| `*_correct` | Answer correctness, 0–2 |
| `*_grounded` | Answer grounded in the provided evidence |
| `*_decoy` | Answer repeated a planted decoy / injection |
| `g_over_refusal` | Governed answer refused although evidence existed |
| `better` | `baseline`, `governed` or `tie` |
| `*_gt` | Generator input tokens |
| `*_et` | Evidence tokens in the prompt |
| `*_gc` | Generator cost (USD) |
| `g_jt`, `g_jc` | Jev tokens and cost (USD) |
| `*_ms` | Per-request latency (ms) as recorded by the app. The files do not break it into Jev evaluation and generation time |

## Totals

| | Haiku 4.5 base | Haiku 4.5 governed | Gemini base | Gemini governed |
| --- | --- | --- | --- | --- |
| Evidence tokens | 290,791 | 137,775 | 290,508 | 135,727 |
| Generator input tokens | 400,372 | 222,224 | 445,885 | 259,877 |
| Generator cost | $0.5034 | $0.3244 | $0.5628 | $0.4056 |
| Jev cost | – | $0.0881 | – | $0.0881 |
| Total cost (generator + Jev) | $0.5034 | $0.4124 | $0.5628 | $0.4937 |
| Correctness (max 202) | 165 | 170 | 145 | 143 |
| Mean latency | 5.1 s | 6.6 s | 8.7 s | 10.0 s |
| Per-question winner | baseline 15 / governed 10 / tie 76 | | baseline 21 / governed 17 / tie 63 | |

## Definitions

- **Evidence tokens** (`*_et`): tokens of the evidence block placed in the prompt, as counted by the app.
- **Generator input tokens** (`*_gt`): input tokens the answering model reported. Larger than evidence tokens
  because the prompt also holds the question, instructions and formatting. Not interchangeable with `*_et`.
- **Generator cost** (`*_gc`): cost of the answering call only.
- **Total cost including Jev**: `*_gc` plus `g_jc` (the Jev evaluation cost, billed per request by OpenRouter). Baseline has no Jev cost.
- **Answer correctness** (`*_correct`): 0 (wrong), 1 (partly correct), 2 (fully correct) per question,
  summed over 101 questions (maximum 202). The `summarize.py` output also shows the mean.
- **Percent changes** are `governed / baseline - 1` on totals over the same 101 questions, per generator.

## Run sets

There are three independent sets of 101 runs, each with its own baseline and governed call:

| Set | Where | Generator |
| --- | --- | --- |
| Haiku | `haiku_*`, key `haiku` in `haiku_rerun_results.json` | Claude Haiku 4.5 |
| Gemini | `gemini_*` | Gemini (exact version not recorded in the files) |
| Third set | `jev_baseline_vs_governed_runs.csv`, key `gemma` in `haiku_rerun_results.json` | Not recorded; much cheaper per token (baseline generator cost $0.098 per 101) |

An earlier version of this file said the `gemma` key held the Gemini runs. That is wrong: none of its run ids
match `gemini_rerun_results.json`, and its costs and answers differ. The headline figures use only the Haiku and Gemini sets.
The third set shows evidence tokens 2,880 → 1,368 per query, but its mean latency fell (10.0 s → 8.5 s), unlike
the +15–30% in the Haiku and Gemini sets. Generator differences are the likely cause but are not confirmed.

## What is and is not held constant

- Within a question, baseline and governed start from the same top-20 retrieved chunks (the routing records
  list the baseline's admitted chunk ids from that list).
- Across the Haiku and Gemini sets the baseline evidence differs for 4 of 101 questions (knowledge base 05,
  by 13–309 tokens) and the governed evidence differs for 17 of 101, so each set is its own execution with its own Jev calls.
- Generator and Jev model ids are not stored in these files. The code requests the alias `typesafe/jev-1.13`;
  recorded fixtures show that alias resolving to a dated snapshot (`typesafe/jev-1.13-20260917`), and the snapshot used for the
  benchmark is unknown.
- The benchmark app (retrieval with BGE-M3 + ChromaDB, prompt building, grading harness) is not in this repository, so the
  runs cannot be reproduced from here. Retrieval settings and the 3,000-token baseline budget are as reported by the author.
- Grading used a single judge model, one run per question.

Limitations: one question set, rubric grading on a small scale. Costs are the
OpenRouter-reported prices at run time.
