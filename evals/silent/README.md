# Vigil Silent-Failure Benchmark

Measures `MCPWatch._is_silent_result` — the detector behind Vigil's positioning as "the MCP
silent-failure watchdog." The number that backs that claim: how reliably does it flag
genuinely-empty tool results (recall) without false-flagging legitimate ones (the
conservative contract)?

## Run

```bash
python3 -m evals.silent.run_evals
```

Deterministic, no deps beyond vigil. Writes `results.json`.

## Metrics

- **Recall** — of genuinely-empty results, the fraction flagged silent. The detection rate.
- **False-positive rate** — of legitimate results, the fraction wrongly flagged. The
  conservative contract demands **0%**: flagging `0`, `False`, or populated dicts trains
  users to ignore the alert, which is worse than a missed silent.
- **Precision, F1.**

## Baseline

`Recall 100% (12/12) · FP-rate 0% (13 legit) · F1 1.00`

The 25 cases cover the real MCP result shapes: raw scalars, CallToolResult-like objects
(`.content` / `.root` / `.isError`), and raw dicts — including the contract traps (`0`,
`False`, `{}`, `{"count": 0}`, image/resource payloads, `isError` results, mixed
content where one item is real).

## Why it passes clean

The detector was hardened deliberately (conservative-by-design: only None / empty /
whitespace-text / empty-content is silent; anything ambiguous is treated as real). This
benchmark is the regression guard that keeps it that way — and the citable detection
number for the watchdog claim.
