# Benchmark results

101 questions over seven public-document knowledge bases (cybersecurity incident response,
procurement, Indian law, climate migration, quantum computing, psychology, corporate reports) in
seven question types (ordinary, exact-identifier, near-miss, false-premise, conflicting-sources,
unanswerable, synthesis). Each question
was answered twice per generator: **baseline** (top-20 retrieved chunks, plain budget fill) and
**governed** (Evidence Governor, `DEFAULT_POLICY`). Retrieval: BGE-M3 + ChromaDB, top-k 20.

| File | Contents |
| --- | --- |
| `haiku_baseline_vs_governed_graded.csv` | Per-question graded results, Claude Haiku 4.5 generator |
| `gemini_baseline_vs_governed_graded.csv` | Same, Gemini generator |
| `jev_baseline_vs_governed_runs.csv` | Per-question run metadata (governor status, tokens, cost, latency) |
| `*_rerun_results.json` | Raw answers and metrics per question and mode |
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
| `*_ms` | End-to-end latency (ms) |

## Totals

| | Haiku 4.5 base | Haiku 4.5 governed | Gemini base | Gemini governed |
| --- | --- | --- | --- | --- |
| Evidence tokens | 290,791 | 137,775 | 290,508 | 135,727 |
| Generator input tokens | 400,372 | 222,224 | 445,885 | 259,877 |
| Generator cost | $0.5034 | $0.3244 | $0.5628 | $0.4056 |
| Jev cost | – | $0.0881 | – | $0.0881 |
| Total cost | $0.5034 | $0.4125 | $0.5628 | $0.4937 |
| Correctness (max 202) | 165 | 170 | 145 | 143 |
| Mean latency | 5.1 s | 6.6 s | 8.7 s | 10.0 s |
| Per-question winner | baseline 15 / governed 10 / tie 76 | | baseline 21 / governed 17 / tie 63 | |

Note: `haiku_rerun_results.json` holds the Gemini runs under the key `gemma` (the same runs as
`gemini_rerun_results.json`); read `gemma` as Gemini.

Limitations: one question set, rubric grading on a small scale. Costs are the
OpenRouter-reported prices at run time.
