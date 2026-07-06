"""Golden set for Vigil's silent-failure detector (MCPWatch._is_silent_result).

Vigil's whole repositioning bet is "the MCP silent-failure watchdog", so the number that
matters is: how reliably does it flag genuinely-empty tool results (recall) WITHOUT
false-flagging legitimate ones (the conservative contract — 0, False, populated dicts,
and any non-text payload must never be called silent)?

Cases cover the real MCP result shapes: raw scalars, CallToolResult-like objects (.content
/.root/.isError), and raw dicts. `expect` is the ground-truth label.
"""

from types import SimpleNamespace as NS


def _text(t):
    """An MCP text content item (object form)."""
    return NS(type="text", text=t)


# Each case: (id, payload, expect_silent, note)
CASES = [
    # ── SILENT: genuinely empty results that should be flagged ──────────────
    ("none",                 None,                                   True,  "tool returned nothing"),
    ("empty_string",         "",                                     True,  None),
    ("whitespace_string",    "   \n\t ",                             True,  "blank text"),
    ("empty_bytes",          b"",                                    True,  None),
    ("empty_list",           [],                                     True,  "no content items"),
    ("dict_empty_content",   {"content": []},                        True,  "MCP result, zero content"),
    ("dict_empty_text",      {"content": [{"type": "text", "text": ""}]}, True, "one empty text item"),
    ("dict_whitespace_text", {"content": [{"type": "text", "text": "  "}]}, True, None),
    ("obj_empty_content",    NS(content=[]),                         True,  "CallToolResult, empty"),
    ("obj_empty_text",       NS(content=[_text("")]),                True,  None),
    ("root_empty_content",   NS(root=NS(content=[], isError=False)), True,  "ServerResult.root path"),
    ("list_all_empty_text",  [{"type": "text", "text": ""}, {"type": "text", "text": "  "}], True, "every item blank"),

    # ── NOT SILENT: the conservative contract — must never be flagged ───────
    ("zero",                 0,                                      False, "0 is a real result, not empty"),
    ("false",                False,                                  False, "False is a real result"),
    ("empty_dict",           {},                                     False, "no content key -> carries data"),
    ("populated_dict_zero",  {"count": 0},                           False, "populated dict with a zero value"),
    ("real_text",            "ok",                                   False, None),
    ("dict_real_text",       {"content": [{"type": "text", "text": "42 rows"}]}, False, None),
    ("image_content",        {"content": [{"type": "image", "data": "iVBOR"}]}, False, "non-text payload = real"),
    ("resource_content",     {"content": [{"type": "resource", "resource": {}}]}, False, "resource payload = real"),
    ("error_dict",           {"isError": True, "content": [{"type": "text", "text": "boom"}]}, False, "error path, not silent"),
    ("error_obj",            NS(isError=True, content=[]),           False, "isError wins over empty content"),
    ("list_of_numbers",      [1, 2, 3],                              False, "non-text items = real payload"),
    ("obj_real_text",        NS(content=[_text("done")]),            False, None),
    ("mixed_one_real",       [{"type": "text", "text": ""}, {"type": "text", "text": "found it"}], False, "one real item is enough"),
]

# The conservative contract: every False case must stay False. A regression that starts
# flagging 0 / False / populated dicts is worse than a missed silent — it's noise that
# trains users to ignore the watchdog.
SILENT_IDS = {c[0] for c in CASES if c[2]}
