"""Recompute every headline benchmark number from the raw files in this folder.

Source of truth for the figures quoted in README.md, SHOWCASE.md and index.html.
Standard library only:  python results/summarize.py
"""

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
N = 101


def rows(name):
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def total(rs, col):
    return sum(float(r[col]) for r in rs)


def pct(base, new):
    return f"{(new / base - 1) * 100:+.1f}%"


def sign_test_p(up, down):
    n, k = up + down, min(up, down)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def answer_chars(file, key):
    runs = json.loads((HERE / file).read_text(encoding="utf-8"))[key]
    return {m: sum(len(r[m]["ans"] or "") for r in runs) for m in ("baseline", "governed")}


for label, file in (("Claude Haiku 4.5", "haiku"), ("Gemini", "gemini")):
    d = rows(f"{file}_baseline_vs_governed_graded.csv")
    assert len(d) == N
    b_et, g_et = total(d, "b_et"), total(d, "g_et")
    b_gt, g_gt = total(d, "b_gt"), total(d, "g_gt")
    b_gc, g_gc, jev = total(d, "b_gc"), total(d, "g_gc"), total(d, "g_jc")
    b_c, g_c = total(d, "b_correct"), total(d, "g_correct")
    up = sum(float(r["g_correct"]) > float(r["b_correct"]) for r in d)
    down = sum(float(r["g_correct"]) < float(r["b_correct"]) for r in d)
    chars = answer_chars(f"{file}_rerun_results.json", file)
    print(f"== {label} ({N} questions) ==")
    print(f"evidence tokens/query   {b_et / N:,.0f} -> {g_et / N:,.0f}  ({pct(b_et, g_et)})")
    print(f"generator input tokens  {b_gt / N:,.0f} -> {g_gt / N:,.0f}  ({pct(b_gt, g_gt)})")
    print(f"generator cost (101)    ${b_gc:.4f} -> ${g_gc:.4f}  ({pct(b_gc, g_gc)})")
    print(f"Jev cost (101)          ${jev:.4f}")
    print(f"total cost incl. Jev    ${b_gc:.4f} -> ${g_gc + jev:.4f}  ({pct(b_gc, g_gc + jev)})")
    print(f"correctness (max 202)   {b_c:.0f} -> {g_c:.0f}  (mean {b_c / N:.2f} -> {g_c / N:.2f})")
    p = sign_test_p(up, down)
    print(f"questions up/down/same  {up}/{down}/{N - up - down}  sign-test p={p:.2f}")
    b_ms, g_ms = total(d, "b_ms"), total(d, "g_ms")
    print(f"mean latency            {b_ms / N / 1000:.1f} s -> {g_ms / N / 1000:.1f} s "
          f"({pct(b_ms, g_ms)})")
    print(f"answer length (chars)   {pct(chars['baseline'], chars['governed'])}\n")

r = rows("jev_baseline_vs_governed_runs.csv")
print("== jev_baseline_vs_governed_runs.csv (separate run set, generator not recorded) ==")
print(f"evidence tokens/query   {total(r, 'b_et') / N:,.0f} -> {total(r, 'g_et') / N:,.0f}")
print(f"Jev requests/query {total(r, 'g_jr') / N:.0f}, tokens {total(r, 'g_jt') / N:,.0f}, "
      f"cost ${total(r, 'g_jc') / N:.6f}")
print(f"mean latency            {total(r, 'b_ms') / N / 1000:.1f} s -> "
      f"{total(r, 'g_ms') / N / 1000:.1f} s")
