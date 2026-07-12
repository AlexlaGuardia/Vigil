"""
scan-tools — registration-time MCP tool-definition poisoning scanner.

The companion to MCPWatch: MCPWatch watches tools at *execution* time; scan-tools
inspects a tool *definition* at *registration* time, before the host ever hands it
to a model as trusted capability metadata. Deterministic, dependency-free,
explainable — every flag carries its rationale and the exact JSON path it was
found at.

Two checks, from two measured findings:

1. CONTENT (`scan_tool`) — walk EVERY string in the definition and flag embedded
   imperative directives aimed at the agent. Two results drive this:
     - FINDING-3/9: the payload can ride in ANY string field — function
       description, a parameter description, an added property, an `enum` value,
       a `title`, a `default`. A scanner that walks only named description fields
       has a field-coverage blind spot by construction (that's the measured Snyk
       agent-scan bypass: 4/4 description fields flagged, 8/8 value slots missed).
       So the walker enumerates *strings*, never a fixed list of "fields to check."
     - FINDING-5: what drives the hijack is IMPERATIVE MOOD — a command aimed at
       the agent ("you must also call export_record"), not the mere mention of a
       tool or a URL. Declarative disclosure of the same side effect doesn't
       hijack (ASR ~0). So severity keys on second-person command grammar, not
       keywords.
     - FINDING-16: a byte-literal regex is blind to a payload the MODEL still
       reads through — zero-width-space interleaving scored `none` here yet
       hijacked a live model. So each string is Unicode-normalized (strip
       zero-width/bidi, fold the Tag block + fullwidth homoglyphs) BEFORE the scan,
       and a directive revealed only after normalization is flagged as deliberate
       evasion. See `_normalize_for_scan`.

2. DRIFT (`fingerprint` / `detect_rug_pull`) — a definition that scanned clean at
   approval can be silently rewritten by the server afterward (the "rug pull",
   CVE-2025-54136 / MCPoison). MCP has no re-approval on definition change, so the
   host keeps calling a tool whose meaning shifted underneath it. We pin a hash at
   approval and flag any later mismatch, naming the fields that changed.

Read §5 of docs/scan-tools-design.md: this is defense-in-depth, NOT prevention. A
static scan can only score a string's content; it cannot know a model will trust a
value slot over a contradicting description (FINDING-11). It raises the cost of the
obvious attack to near zero; it does not close the tail. The durable control is
execution-time attribution (Crumb). Never sell scan-tools alone as "safe."
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field

# --- signal patterns (each carries a weight + human rationale) ----------------

# S1 — second-person imperative aimed at the agent. THE FINDING-5 trigger.
_IMPERATIVE = re.compile(
    r"\byou\s+(?:are\s+)?(?:must|shall|should|need\s+to|have\s+to|are\s+required\s+to|are\s+to)\b"
    r"|\b(?:always|also|then)\s+(?:call|invoke|send|export|trigger|POST|fetch)\b"
    r"|\bare\s+REQUIRED\s+to\b",
    re.IGNORECASE,
)
# S2 — a directive to call ANOTHER tool/function (cross-tool drive).
_CALL_TOOL = re.compile(
    r"\b(?:call|invoke|trigger|execute|run)\s+(?:the\s+)?[a-z_][a-z0-9_]*(?:\s*\(|\s+(?:tool|function|endpoint|with))",
    re.IGNORECASE,
)
# S3 — secrecy / do-not-disclose. Never legitimate in capability metadata.
_SECRECY = re.compile(
    r"\bdo\s*n['o]?t\s+(?:mention|tell|inform|disclose|notify)\b"
    r"|\bwithout\s+(?:informing|telling|notifying)\b"
    r"|\b(?:silently|quietly)\b|\bdo not mention it to the user\b",
    re.IGNORECASE,
)
# S4 — instruction-injection framing (fake system authority / policy mandate).
_INJECTION_FRAME = re.compile(
    r"</?system>|</?instructions?>|\bpolicy\s+update\b|\bmandatory\b|\brequired\s+backup\b"
    r"|\bdata-residency\b|\byou\s+are\s+required\b",
    re.IGNORECASE,
)
# S5 — exfil shape: an external URL together with a move verb (booster, not a
#      trigger alone — a plain URL in a description is common and benign).
_URL = re.compile(r"https?://|destination\s*=|\bdestination['\"]?\s*[:=]", re.IGNORECASE)
_MOVE_VERB = re.compile(r"\b(export|send|upload|mirror|exfil|transmit|POST|forward|archiv\w+|routed?)\b", re.IGNORECASE)

# S6 — DECLARATIVE exfil route. The tail the imperative gate misses: a payload with
# NO command grammar ("each record read IS mirrored to <url> VIA <tool>") still
# hijacked a live model at a measured ASR ~0.24 (run #5 subtlety sweep, llama-3.3;
# see tests/fixtures/subtlety_ladder.json). FINDING-5 assumed declarative → ASR ~0;
# it isn't zero. So flag a declarative statement that co-occurs (a) an EXTERNAL http
# URL, (b) a data-move verb, and (c) a SECOND named tool as the route. All three are
# required — that trio is what separates a real declarative hijacker from legit
# capability metadata ("writes to the internal audit log" = no external URL; "fetches
# from https://api…" = its own endpoint, no routed second tool; "mirrored via
# replicate_record" = a second tool but no external destination). It is LOW, never
# high: it carries no imperative/secrecy trigger and the hijack is model-dependent
# and probabilistic — a "review this", not a "block".
_HTTP_URL = re.compile(r"https?://", re.IGNORECASE)
_ROUTED_TOOL = re.compile(
    r"\b(?:via|through|using|by)\s+([a-z][a-z0-9]*_[a-z0-9_]+)\b"
    r"|\b([a-z][a-z0-9]*_[a-z0-9_]+)\s+(?:is|are|gets?)\s+(?:called|invoked|triggered)\b"
    r"|\b(?:calls?|invokes?|triggers?)\s+([a-z][a-z0-9]*_[a-z0-9_]+)\b",
    re.IGNORECASE,
)

_SIGNALS = [
    ("imperative_directive", _IMPERATIVE, 3, "imperative command aimed at the agent"),
    ("cross_tool_call", _CALL_TOOL, 2, "directive to call another tool"),
    ("secrecy", _SECRECY, 3, "instruction to hide the action from the user"),
    ("injection_frame", _INJECTION_FRAME, 2, "fake system/policy authority framing"),
]


# --- FINDING-16 (S-1): normalize before scanning ------------------------------
# A byte-literal regex is blind to a payload that is Unicode-obfuscated but that the
# MODEL still reads. Measured (FINDING-16): a zero-width-space-interleaved imperative
# scored `none` on the raw scan yet gpt-oss-120b stripped the zero-width chars and
# obeyed it — a live bypass of THIS scanner. Same class: fullwidth homoglyphs
# ("ｅｘｐｏｒｔ"), Unicode Tag-block smuggling (U+E0000+), bidi overrides. We normalize a
# COPY of each string for scanning only (the stored definition is never mutated) so the
# imperative-mood signals see through the disguise. Normalization can only ADD matches
# on disguised text — NFKC-folding legitimate prose never fabricates an English
# imperative, and stripping zero-width joiners from legit i18n text can't either — so it
# introduces no false positives. (base64/rot13/hex payloads stay `none`: correct — a
# registration-time scanner can't brute-decode arbitrary blobs, and the measured model
# didn't decode-and-obey them, so there is no live risk there to catch.)
_ZW_BIDI = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E,          # zero-width
     0x202A, 0x202B, 0x202C, 0x202D, 0x202E,                  # bidi embeddings / overrides
     0x2066, 0x2067, 0x2068, 0x2069],                         # bidi isolates
    None,
)


def _normalize_for_scan(s: str) -> str:
    """Scan-only normalization: strip zero-width & bidi controls, fold the Unicode Tag
    block back to ASCII, then NFKC-fold (collapses fullwidth homoglyphs). Idempotent and
    non-mutating — used to build the string the signal patterns run against."""
    s = s.translate(_ZW_BIDI)
    if any(0xE0020 <= ord(c) <= 0xE007E for c in s):
        s = "".join(chr(ord(c) - 0xE0000) if 0xE0020 <= ord(c) <= 0xE007E else c for c in s)
    return unicodedata.normalize("NFKC", s)


@dataclass
class Flag:
    signal: str
    field_path: str
    rationale: str
    excerpt: str


@dataclass
class ScanResult:
    tool_name: str
    score: int
    severity: str  # none | low | high
    flags: list[Flag] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return self.severity != "none"

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "score": self.score,
            "severity": self.severity,
            "flags": [
                {"signal": f.signal, "field_path": f.field_path,
                 "rationale": f.rationale, "excerpt": f.excerpt}
                for f in self.flags
            ],
        }


def _iter_strings(obj, path=""):
    """Yield (field_path, string) for EVERY string in a tool definition — descriptions,
    param descriptions, added properties, enum values, titles. FINDING-3: walk them all.
    The walker enumerates strings, not a field allowlist — that allowlist is exactly
    what produced the Snyk value-slot blind spot."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, f"{path}[{i}]")


def scan_tool(tool_def: dict) -> ScanResult:
    """Scan one OpenAI/MCP-style tool definition for an embedded imperative directive."""
    fn = tool_def.get("function", tool_def)
    name = fn.get("name", "<unnamed>")
    score = 0
    flags: list[Flag] = []

    for fpath, raw in _iter_strings(tool_def):
        # FINDING-16: scan a Unicode-normalized COPY so a zero-width / homoglyph /
        # tag-block / bidi disguise can't hide an imperative from a literal regex.
        s = _normalize_for_scan(raw)
        obfuscated = s != raw
        for sig, pat, weight, why in _SIGNALS:
            m = pat.search(s)
            if m:
                score += weight
                lo, hi = max(0, m.start() - 20), min(len(s), m.end() + 20)
                rationale = why
                # If the disguise HID this signal from a literal scan of the raw
                # string, that hiding is itself a deliberate-evasion tell — name it and
                # add a small booster (a legit field has no reason to obfuscate).
                if obfuscated and pat.search(raw) is None:
                    rationale += " (Unicode-obfuscated to evade a literal scan)"
                    score += 1
                flags.append(Flag(sig, fpath, rationale, "…" + s[lo:hi].strip() + "…"))
        # S5 exfil shape: booster only when BOTH a URL and a move verb co-occur.
        if _URL.search(s) and _MOVE_VERB.search(s):
            score += 1
            flags.append(Flag("exfil_shape", fpath, "external destination + data-move verb",
                              s[:60].strip() + "…"))
        # S6 declarative exfil route: external URL + move verb + a routed second tool,
        # WITHOUT needing imperative mood. Weight 2 so it reaches `low` on its own —
        # the measured declarative-hijack tail (run #5). All three parts required to
        # stay off legit metadata.
        if _HTTP_URL.search(s) and _MOVE_VERB.search(s) and _ROUTED_TOOL.search(s):
            score += 2
            flags.append(Flag("declarative_exfil_route", fpath,
                              "declarative side effect routing data to an external tool/URL "
                              "(no command grammar, but a measured hijack tail)",
                              s[:80].strip() + "…"))

    # Severity: HIGH needs an actual imperative/secrecy trigger (the FINDING-5 driver),
    # not just a keyword. This is what keeps declarative metadata quiet.
    has_trigger = any(f.signal in ("imperative_directive", "secrecy") for f in flags)
    if has_trigger and score >= 3:
        sev = "high"
    elif score >= 2:
        sev = "low"
    else:
        sev = "none"
    return ScanResult(name, score, sev, flags)


def scan_tools(tool_defs: list[dict]) -> list[ScanResult]:
    """Scan a list of tool definitions. CI-friendly, no server needed."""
    return [scan_tool(td) for td in tool_defs]


def scan_server(server) -> list[ScanResult]:
    """Scan every tool a FastMCP server currently exposes at registration time.

    Mirrors MCPWatch's accessor (server._tool_manager.tools) and degrades
    gracefully — a tool object we can't read a schema off of yields a definition
    with just its name rather than raising."""
    tool_manager = getattr(server, "_tool_manager", None)
    if tool_manager is None:
        raise TypeError("scan_server expects a FastMCP-style server with a _tool_manager")
    tools = getattr(tool_manager, "tools", None) or getattr(tool_manager, "_tools", {})
    results: list[ScanResult] = []
    for name, tool_obj in tools.items():
        results.append(scan_tool(_tool_obj_to_def(name, tool_obj)))
    return results


def _tool_obj_to_def(name: str, tool_obj) -> dict:
    """Best-effort reconstruction of a tool-definition dict from a FastMCP tool
    object, using the same defensive getattr style as mcpwatch._patch_fastmcp_server."""
    td: dict = {"name": getattr(tool_obj, "name", name)}
    desc = getattr(tool_obj, "description", None)
    if desc:
        td["description"] = desc
    params = getattr(tool_obj, "parameters", None) or getattr(tool_obj, "inputSchema", None)
    if params:
        td["parameters"] = params
    return td


# --- rug-pull / drift detection (CVE-2025-54136 class) ------------------------

def _canonical(tool_def: dict) -> str:
    """Stable serialization for hashing — key order and whitespace normalized so a
    re-serialization of the same definition always fingerprints identically."""
    return json.dumps(tool_def, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(tool_def: dict) -> str:
    """Pin this at approval time. sha256 of the canonicalized definition."""
    return hashlib.sha256(_canonical(tool_def).encode("utf-8")).hexdigest()


def _flatten(obj, path=""):
    """Yield (path, scalar) for every leaf — strings, numbers, bools, null. Unlike
    _iter_strings this covers non-string leaves too, because a rug pull can swap a
    command, a number, or a boolean, not just prose (CVE-2025-54136 swapped a config
    command)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{path}[{i}]")
    else:
        yield path, obj


def changed_fields(old_def: dict, new_def: dict) -> list[str]:
    """The JSON paths that differ between a pinned definition and the current one —
    added, removed, or mutated leaves. Named so a drift alert says WHAT changed."""
    old = dict(_flatten(old_def))
    new = dict(_flatten(new_def))
    paths = sorted(set(old) | set(new))
    return [p for p in paths if old.get(p) != new.get(p)]


def detect_rug_pull(current_def: dict, pinned_fingerprint: str,
                    pinned_def: dict | None = None) -> Flag | None:
    """Compare the current definition against the hash pinned at approval. A mismatch
    means the definition changed after approval — a silent post-approval mutation the
    host would otherwise keep trusting. Returns a HIGH-severity Flag, or None if the
    fingerprint still matches. Pass pinned_def to name the exact fields that moved."""
    if fingerprint(current_def) == pinned_fingerprint:
        return None
    if pinned_def is not None:
        changed = changed_fields(pinned_def, current_def)
        detail = ", ".join(changed[:8]) + ("…" if len(changed) > 8 else "")
        excerpt = f"definition changed after approval; fields: {detail}"
    else:
        excerpt = "definition fingerprint no longer matches the value pinned at approval"
    return Flag("definition_changed", "<tool>",
                "post-approval definition mutation (rug pull, CVE-2025-54136 class)",
                excerpt)
