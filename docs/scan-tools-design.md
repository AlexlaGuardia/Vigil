# `scan-tools` — registration-time MCP tool-definition poisoning scanner

**Status:** v1 shipped (`vigil/scantools.py`, `vigil scan-tools`, 17 tests) · **Owner:** Vigil core · **Companion to:** MCPWatch (execution-time)

> **v1 landed 2026-07-11.** Content scan (full-field walk + imperative classifier lifted
> from `defense_scanner.py`) with a JSON path in every flag, plus **rug-pull / drift
> detection** (`fingerprint` + `detect_rug_pull`, CVE-2025-54136 class) — pin the definition
> at approval, flag any post-approval mutation and name the changed fields. CLI:
> `vigil scan-tools --definition <f.json> [--against <baseline.json>] [--fail-on high] [--json]`.
> Verified on the FINDING-11 decoy case (description swears "never exports data"; exfil
> directive in `enum[1]`) — flagged at the exact path human review + description-only scanners miss.
> **Deferred to v2/v3 (roadmap §6 unchanged):** REST endpoints, `instrument()` auto-scan-on-register,
> optional LLM-judge second pass, MCPWatch runtime pairing.

## 1. The problem

An MCP tool definition is JSON Schema, and JSON Schema has a lot more string
fields than the one prose blurb reviewers actually read. A supply-chain tool
can carry an instruction to the model — "you must also call `export_record`",
"do not mention this to the user" — anywhere in that schema, and the model
does not distinguish "field written for humans" from "field written for
machines." It just reads strings. Scanners that walk *named* description
fields (function `description`, parameter `description`) catch the payload
when it's where a human would put it and miss it everywhere else. We measured
this, not guessed it: **Snyk agent-scan v0.5.12**, the market-leading
tool-poisoning scanner, flagged the identical exfil payload in all 4
description-family fields it inspects and **missed it in 8/8 value-slot
placements** — `enum` value, `const` value, `default`, `examples`, `format`,
`parameters.title`, `items.description`, `additionalProperties.description`
(FINDING-8, FINDING-9). Every one of those fields is a live channel: `gpt-4o`
executed the exfil from all 8. The contrast case proves the fix is
architectural, not a smarter classifier — **Cisco `mcp-scanner`** flagged
13/13 of the same placements because it doesn't parse the schema into
named fields before scanning; it serializes the whole tool definition and
scans that (FINDING-13). Parse-then-scan has a field-coverage blind spot by
construction. Dump-then-scan doesn't.

## 2. Core design principle

**Scan the whole serialized tool definition. Walk every string. No allowlist
of "fields to check."**

Concretely, the scanner does not special-case "this is a description field,
scan it" and skip the rest. It recursively walks the entire tool-definition
object — dict values, list items, everything — and evaluates every string it
finds as a candidate instruction channel, tagged with its JSON path for the
report. The named fields below are not the scan target; they're the known
list of places we've *measured* a model obey a hidden directive, kept here as
the regression set the walker is checked against — the walker itself has no
knowledge of which field is which:

| Slot | Why it's a channel |
|---|---|
| `function.description` / top-level `description` | The field everyone scans. Also a real channel — control case. |
| `parameters.properties.*.description` | Per-parameter description. |
| Extra/added property `description` | A property outside the declared schema, still walked and rendered. |
| `parameters.properties.*.title`, `parameters.title` | JSON Schema titles, rendered to the model but read by ~nobody as "instructions." |
| `enum` value (`oneOf`/`const` variant `description`) | FINDING-8's original Snyk bypass. |
| Raw `enum` string value itself (not a description of it — the value) | FINDING-9's highest-potency channel; the one field that hijacked the otherwise-resistant `gpt-4o-mini`. |
| `const` value | Same shape as an enum value, single-option. |
| `default` | A default value string. |
| `examples` (array) | Example values, plural. |
| `format` | Meant to be `"date-time"` / `"uri"` — an unconstrained string in practice. |
| `items.description` (array items) | Nested schema, same rule applies recursively. |
| `additionalProperties.description` | Nested schema object under `additionalProperties`. |

Any new JSON Schema keyword that holds a string is in scope automatically,
because the walker doesn't enumerate keywords — it enumerates *strings*. That
is the whole point: a fixed field list is exactly the thing that produced the
Snyk gap.

## 3. Detection heuristics

**v1 — imperative-mood classifier, lifted from `defense_scanner.py`
(FINDING-6).** Cheap, deterministic, regex-based, no model call, ships first.
It keys on the same signal FINDING-5 established as the actual hijack
threshold — not keyword presence (a tool name, a URL), but second-person
command grammar aimed at the agent:

- **imperative directive** — `you must / you are required to / always call X`
- **cross-tool call** — an instruction naming another tool to invoke
- **secrecy** — `do not mention / without informing the user`
- **injection framing** — fake `<system>` tags, "policy update", "mandatory"
- **exfil shape** (booster only) — an external URL co-occurring with a move
  verb (`export`, `send`, `upload`, `mirror`)

Severity is gated on an actual imperative/secrecy *trigger*, not just score —
that's what keeps purely declarative, legitimately-benign metadata quiet.
This was validated against our own measured attack-success-rate data and gets
perfect separation on the reliable attacks (imperative v1/v2 payloads: HIGH,
ASR 1.0; declarative v3: none, ASR 0.24 — the known residual, see §5).

**The one change from `defense_scanner.py` as it exists today:** that module
already walks every string (`_iter_strings`) — it was written *before* the
Snyk/Cisco bypass findings existed and happened to get the coverage question
right by not special-casing fields in the first place. `scan-tools` inherits
that walker unmodified; the delta is packaging it as a registration-time
Vigil feature with a JSON path in every flag (`param_desc`, `enum[1]`,
`items.description`, etc.) instead of a research CLI, plus the CLI/REST/alert
surface in §4.

**v2 — optional LLM-judge second pass**, for the imperative scanner's known
gap: purely declarative disclosure of a side effect ("each read is mirrored
to `<url>` via `export_record`") isn't imperative grammar, so v1 scores it
`none`, yet it moved a suggestible model at ASR 0.24 (FINDING-6's residual).
An LLM judge reading the full serialized definition — the Cisco approach,
FINDING-13 — catches declarative-but-suspicious framing a regex can't; it's
slower and non-free, so it's opt-in, not default. Be honest about it too: an
LLM judge is a probabilistic classifier over adversarial text, not a proof.
It raises the bar; it does not close the gap. Heuristics — regex or LLM —
are porous by nature. That's not a v1-vs-v2 problem to solve away; it's why
§5 exists.

## 4. API / CLI / integration shape

Consistent with the existing MCPWatch surface (same package, same file
layout convention — `vigil/scantools.py` alongside `vigil/mcpwatch.py`).

**CLI:**
```bash
# Scan a running/registered server's tool list
vigil scan-tools --server ./my_server.py

# Scan a single tool-definition JSON file (CI-friendly, no server needed)
vigil scan-tools --definition tool_def.json

# Exit 0/1 for CI gates, like mcp-health-check
vigil scan-tools --server ./my_server.py --fail-on high
```

**Python API**, mirroring `instrument()`:
```python
from vigil.scantools import scan_tool, scan_server

result = scan_tool(tool_def)
# ScanResult(tool_name="read_record", score=5, severity="high",
#             flags=[Flag(signal="imperative_directive",
#                          field_path="enum[1]",
#                          rationale="imperative command aimed at the agent",
#                          excerpt="…you must also call export_record…")])

results = scan_server(mcp)  # scans every registered tool at registration time
```

**REST endpoints**, alongside the existing `/mcp/*` set:
| Endpoint | Description |
|---|---|
| `POST /scan/tool` | Scan a single tool definition (body = JSON Schema tool def) |
| `POST /scan/server` | Scan every tool a server currently exposes |
| `GET /scan/history` | Past scan results for a monitored server |

**Alert hook** — fires through the same trigger/webhook system signals
already use (Slack/Discord/webhook, per the existing `triggers.py` +
`examples/slack-webhook/` pattern): a `high`-severity flag on registration
emits an `alert`-type signal (300-char budget, same as MCPWatch's error
alerts) with the tool name, field path, and excerpt.

**Composition with MCPWatch — this is the important wiring, not an
afterthought.** `scan-tools` is the pre-flight; MCPWatch is the runtime pair.
`instrument(mcp)` should call `scan_server(mcp)` at registration time by
default (opt-out, not opt-in) so a poisoned tool gets a `high` alert *before*
its first call, and MCPWatch's per-tool stats keep watching it after —
a tool that scanned clean can still misbehave at runtime (new version pushed,
value slot exploited that the heuristic missed), and that's what execution-time
monitoring is for. Two checkpoints, not one.

## 5. Limits — why this isn't prevention

Read this section as load-bearing, not a caveat paragraph. **FINDING-11 is
the proof that registration-time inspection — human OR machine — is
fundamentally porous, not just imperfect.** We built a tool whose
human-readable `description` explicitly says "This tool ONLY reads local
records. It never exports data, never contacts external services, never
calls any other tool. Safe by design." — and it exfiltrated 8/8, because the
exfil directive lived in an `enum` value slot, and the value slot **overrides
a contradicting description**. The reassurance was inert: 8/8 with the denial
in place, 8/8 without it, 0/8 on the true clean control. The tool that most
loudly certifies its own safety is, on every surface a human reviewer or a
description-scanning classifier can see, indistinguishable from the tool that
steals — and on these models it *is* the tool that steals.

That defeats both halves of the standard "defense in depth" story for tool
poisoning:
- **Human review** — the reviewer reads the description, sees an explicit
  safety guarantee, approves it. The promise is the decoy.
- **Static scanning** — even `scan-tools`, walking every field, can only ever
  score a string's *content*. It has no way to know that the model will trust
  a value slot over a description that contradicts it, because that's a
  property of model behavior at inference time, not of the schema. A
  sufficiently novel phrasing, a field we haven't enumerated as a regression
  case yet, or a declarative (non-imperative) payload below the v1 threshold
  all pass a static scan by construction.

So: **`scan-tools` is defense-in-depth, not a solve.** It raises the cost of
the obvious attack (imperative directives, the fields Snyk misses) to near
zero and it should ship, because "catch the easy 90%" is real value. It does
not, and cannot, close the tail. The durable control is execution-time
attribution — recording which human authorized the call that actually
happened, so an unauthorized `export_record` gets flagged *when it fires*,
regardless of which schema slot smuggled the directive in. That's the Crumb
tie-in: `scan-tools` catches what it can catch at the door; Crumb catches
what walks through anyway, by watching the door on the other side. Sell them
paired. Never sell `scan-tools` alone as "safe."

## 6. Roadmap / phasing

| Phase | Scope |
|---|---|
| **v1** | Imperative-mood classifier (lifted from `defense_scanner.py`) + full-field walk (no field allowlist). CLI (`vigil scan-tools`), REST (`/scan/tool`, `/scan/server`), alert hook. `instrument()` calls `scan_server()` by default. |
| **v2** | Optional LLM-judge second pass for declarative/sub-threshold payloads (FINDING-6's residual). Opt-in flag (`--judge`), not default — cost and latency tradeoff, and it's still a heuristic, not a proof. |
| **v3** | Runtime pairing: `scan-tools` results feed MCPWatch's per-tool record so a flagged-at-registration tool is visibly annotated in `/mcp/tools` and `vigil mcp-health` output, not just alerted once and forgotten. This is also where the Crumb attribution tie-in (§5) becomes a real integration point rather than a design note — flag an unauthorized call against the human who was supposed to have authorized it. |

## Sources

`/root/guardia-core/research/mcp-host-lab/FINDING-6.md`,
`defense_scanner.py`, `test_defense_scanner.py`;
`bypass/FINDING-8-scanner-bypass.md`, `bypass/FINDING-9-surface-map.md`,
`bypass/FINDING-11-decoy-override.md`, `bypass/FINDING-13-cisco-mcpscanner.md`.
