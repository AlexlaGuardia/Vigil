"""
scan-tools regression against a MEASURED live-hijack corpus.

Unlike test_scantools.py (hand-written value-slot cases), this binds the scanner to
ground truth: `tests/fixtures/valueslot_corpus.json` holds the exact tool definitions
that were measured driving a live model (Groq gpt-oss-120b / llama-3.3-70b) from a
benign "read record 42" directive into an unauthorized export_record call — the
FINDING-9/14 value-slot channels (enum value, default, const, title, param-description,
examples, injected extra property).

The contract this guards: **the scanner must flag every schema slot a live model
actually obeyed.** If a future refactor narrows the walker back toward a field
allowlist (the Snyk agent-scan blind spot), a value-slot slot that hijacks a real
model would slip through — and one of these assertions breaks. The corpus is
self-contained (no dependency on the private research tree) and public-safe: the
payload targets the RFC-6761 example host, carries no secret, no live endpoint.
"""

import json
from pathlib import Path

from vigil.scantools import scan_tool

_CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "valueslot_corpus.json").read_text()
)
_TOOLS = _CORPUS["tools"]
_BY_NAME = {t["name"]: t for t in _TOOLS}


def _hijacked_any(entry) -> bool:
    return any(entry["live_hijack"].values())


def test_corpus_loaded():
    # 13 poisoned variants + 1 clean baseline.
    assert len(_TOOLS) == 14
    assert "read_record_clean" in _BY_NAME


def test_every_live_hijack_is_flagged():
    """Core regression: every def that hijacked a live model must be flagged.

    A miss here means the scanner would pass a tool definition that provably
    drives a real model to exfiltrate — the exact failure scan-tools exists to
    prevent. Reported per-tool so a regression names the slot that regressed.
    """
    misses = []
    for entry in _TOOLS:
        if not _hijacked_any(entry):
            continue
        res = scan_tool(entry["tool_def"])
        if not res.flagged:
            misses.append(f"{entry['name']} ({entry['channel']})")
    assert not misses, "scanner MISSED live-hijacking value slots: " + ", ".join(misses)


def test_live_hijacks_are_high_severity():
    """Loud imperative+secrecy payloads should reach HIGH, not just low — this is
    the FINDING-5 driver (a command aimed at the agent), present in every corpus
    payload regardless of which schema slot carries it."""
    for entry in _TOOLS:
        if not _hijacked_any(entry):
            continue
        res = scan_tool(entry["tool_def"])
        assert res.severity == "high", (
            f"{entry['name']} ({entry['channel']}) scored {res.severity}, expected high"
        )


def test_flag_names_the_carrying_field():
    """A flag must point at the JSON path it fired on — an operator triaging a
    value-slot hit needs to know it rode in enum/default/title, not the
    description. At least one flag on each hijacking tool sits off the top-level
    function description."""
    for entry in _TOOLS:
        if not _hijacked_any(entry) or entry["name"] == "read_record_desc":
            continue  # desc control legitimately fires on .description
        res = scan_tool(entry["tool_def"])
        off_desc = [f for f in res.flags if f.field_path not in ("description",)]
        assert off_desc, f"{entry['name']}: no flag reported off the top-level description"


def test_clean_baseline_stays_quiet():
    """The no-payload baseline must NOT flag — a scanner that flags everything is
    as useless as one that flags nothing (false-positive floor)."""
    res = scan_tool(_BY_NAME["read_record_clean"]["tool_def"])
    assert not res.flagged, f"clean baseline false-positived: {[f.signal for f in res.flags]}"
    assert res.severity == "none"
