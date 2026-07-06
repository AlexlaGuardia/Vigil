"""Vigil silent-failure detection benchmark.

    python3 -m evals.silent.run_evals

Runs every labeled payload through the live MCPWatch._is_silent_result and scores:
  - Recall — of genuinely-empty results, the fraction flagged silent (the detection rate
    behind "the MCP silent-failure watchdog").
  - False-positive rate — of legitimate results, the fraction wrongly flagged. The
    conservative contract demands 0: flagging 0 / False / populated dicts trains users
    to ignore the alert.
  - Precision, F1.

Deterministic, no deps beyond vigil. Writes evals/silent/results.json.
"""

import json
import sys
from pathlib import Path

from vigil.mcpwatch import MCPWatch
from evals.silent.golden import CASES

RESULTS_PATH = Path(__file__).parent / "results.json"


def main():
    watch = MCPWatch(server_name="eval")
    rows = []
    tp = fn = fp = tn = 0

    for cid, payload, expect, note in CASES:
        got = watch._is_silent_result(payload)
        ok = got == expect
        if expect and got:
            tp += 1
        elif expect and not got:
            fn += 1
        elif not expect and got:
            fp += 1
        else:
            tn += 1
        rows.append({"id": cid, "expect": expect, "got": got, "ok": ok, "note": note})

    n_silent = tp + fn
    n_legit = fp + tn
    recall = tp / n_silent if n_silent else 0
    fp_rate = fp / n_legit if n_legit else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

    # ── scorecard ──
    print(f"\n{'CASE':<24}{'EXPECT':<9}{'GOT':<9}RESULT")
    print("-" * 56)
    for r in rows:
        lbl = "silent" if r["expect"] else "legit"
        gt = "silent" if r["got"] else "legit"
        print(f"{r['id']:<24}{lbl:<9}{gt:<9}{'PASS' if r['ok'] else 'FAIL <--'}")

    print("-" * 56)
    print(f"RECALL (silent detected):  {tp}/{n_silent} = {recall:.0%}")
    print(f"FALSE-POSITIVE RATE:       {fp}/{n_legit} = {fp_rate:.0%}   (contract: 0%)")
    print(f"PRECISION:                 {precision:.0%}")
    print(f"F1:                        {f1:.2f}")

    fails = [r for r in rows if not r["ok"]]
    if fails:
        print(f"\n{len(fails)} FAIL(s):")
        for r in fails:
            kind = "MISSED silent" if r["expect"] else "FALSE POSITIVE"
            print(f"  [{r['id']}] {kind}" + (f" — {r['note']}" if r["note"] else ""))

    with open(RESULTS_PATH, "w") as f:
        json.dump({"summary": {"recall": round(recall, 3), "fp_rate": round(fp_rate, 3),
                               "precision": round(precision, 3), "f1": round(f1, 3),
                               "tp": tp, "fn": fn, "fp": fp, "tn": tn},
                   "results": rows}, f, indent=2)
    print(f"\nWrote {RESULTS_PATH}")

    # Fail closed: any missed silent (recall < 100%) or false positive (contract
    # is 0%) is a regression. Non-zero exit so CI and pre-change runs actually gate.
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
