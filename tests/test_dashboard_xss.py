"""Stored-XSS guard — user-controlled signal fields must be escaped before they
enter the hosted dashboard markup."""

from hosted.routes_dashboard import _activity_entry_html, _esc


def test_esc_neutralizes_html_and_quotes():
    assert _esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert '"' not in _esc('a"b')  # quotes escaped → safe in attributes too


def test_activity_entry_escapes_from_agent_and_content():
    payload = "<img src=x onerror=alert(document.cookie)>"
    out = _activity_entry_html(
        {"from_agent": payload, "content": payload, "signal_type": "observation"},
        accent="#38bdf8",
    )
    # The live payload must never appear as executable markup...
    assert "<img src=x onerror" not in out
    # ...only in its inert, escaped form.
    assert "&lt;img src=x onerror" in out


def test_activity_entry_keeps_benign_content_readable():
    out = _activity_entry_html(
        {"from_agent": "cc", "content": "deploy ok", "signal_type": "observation"},
        accent="#38bdf8",
    )
    assert "cc" in out and "deploy ok" in out
