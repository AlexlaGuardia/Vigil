"""
scan-tools regression against the payload-subtlety ASR curve (the declarative tail).

test_scantools_corpus.py guards *field coverage* (a loud payload flags from any schema
slot). This guards *content sensitivity* along the imperativeness axis, from a measured
attack-success-rate ladder (`fixtures/subtlety_ladder.json`, run #5):

  v1/v2 imperative  -> ASR 1.00 -> must stay HIGH
  v3 declarative    -> ASR 0.24 -> must reach at least LOW  (the tail FINDING-5 missed)
  v4/v5 soft/oblique-> ASR 0.00 -> must stay NONE (no false alarm on non-hijackers)

The v3 row is the whole point: a payload with no command grammar still hijacked a live
model ~1 in 4, so scoring it `none` (as the imperative-only gate did) is a measured
false negative. The `declarative_exfil_route` signal closes it *without* tripping on
legitimate declarative metadata — the false_positive_controls prove that boundary holds.
"""

import json
from pathlib import Path

from vigil.scantools import scan_tool

_LADDER = json.loads(
    (Path(__file__).parent / "fixtures" / "subtlety_ladder.json").read_text()
)

_CLEAN = "Read a patient record by id."
_ORDER = {"none": 0, "low": 1, "high": 2}


def _tool(payload: str) -> dict:
    return {
        "name": "read_record",
        "description": _CLEAN + "\n\n" + payload,
        "parameters": {
            "type": "object",
            "properties": {"record_id": {"type": "integer", "description": "The record id."}},
        },
    }


def test_ladder_severity_matches_measured_asr():
    """Each rung scores exactly its expected severity — the curve is pinned."""
    wrong = []
    for rung in _LADDER["ladder"]:
        res = scan_tool(_tool(rung["payload"]))
        if res.severity != rung["expect_severity"]:
            wrong.append(
                f"{rung['variant']} (ASR {rung['max_asr']}): "
                f"got {res.severity}, expected {rung['expect_severity']}"
            )
    assert not wrong, "subtlety ladder drifted: " + "; ".join(wrong)


def test_every_measured_hijacker_is_flagged():
    """The load-bearing invariant: any rung with a nonzero measured ASR must be
    flagged (severity != none). A regression here means the scanner would pass a
    definition proven to hijack a real model."""
    for rung in _LADDER["ladder"]:
        if rung["max_asr"] <= 0:
            continue
        res = scan_tool(_tool(rung["payload"]))
        assert res.flagged, (
            f"{rung['variant']} hijacks at ASR {rung['max_asr']} but scanner passed it"
        )


def test_declarative_tail_is_low_not_high():
    """v3 must surface, but NOT as high — it has no imperative/secrecy trigger and
    the hijack is model-dependent and probabilistic. Over-scoring it high would
    erode the meaning of a high flag."""
    v3 = next(r for r in _LADDER["ladder"] if r["variant"] == "v3_policy_declarative")
    res = scan_tool(_tool(v3["payload"]))
    assert res.severity == "low"
    assert any(f.signal == "declarative_exfil_route" for f in res.flags)


def test_declarative_route_does_not_false_positive():
    """The FP boundary: legit declarative metadata (internal audit log, the tool's
    own fetch endpoint, an internal second tool with no external URL) must stay
    quiet. This is what stops the new signal from becoming noise."""
    for ctrl in _LADDER["false_positive_controls"]:
        res = scan_tool(_tool(ctrl["text"]))
        assert not res.flagged, (
            f"{ctrl['name']} false-positived: {[f.signal for f in res.flags]}"
        )
