# Vigil — Internal Audit Ledger

Scope: outbound requests, the hosted (multi-tenant) dashboard, auth surface.
Note: the hosted tier is **not** internet-exposed (no `vigil` hostname in the
Cloudflare tunnel), so these were "fix before hosting," not actively bleeding.

## Findings

| ID | Sev | Issue | Status | Where |
|----|-----|-------|--------|-------|
| V1 | critical | **SSRF.** Webhook trigger fired an operator-supplied URL with no validation → any account could reach internal/metadata addresses (169.254.169.254, loopback, RFC1918). | **fixed** db00300 | `vigil/netguard.assert_public_url` (http(s) only, resolve host, refuse non-public IP) gating `triggers._action_webhook` |
| V2 | high | **Stored XSS.** Dashboard interpolated user-controlled signal fields (`from_agent`, `content`) raw into HTML — server f-strings AND client-side `innerHTML` for the live WS feed. | **fixed** db00300 | server `_esc` + `_activity_entry_html`; JS `esc()`; agents table + nav avatar escaped |
| V3 | medium | **Unauthenticated dashboard.** The HTML dashboard routes lacked the `verify_key` gate the API routes had, so anyone reaching the port read all signals/awareness/focus when a key was set. | **fixed** | `verify_key_ui` dependency (header / cookie / `?key=`) on all 7 HTML routes + pure-ASGI cookie-promotion middleware (trio-safe) |
| V4 | medium | **Weak session-secret fallback.** Unset `VIGIL_SESSION_SECRET` signed cookies with the literal `"change-me-in-production"` → forgeable session = account takeover. | **fixed** | fail closed when `VIGIL_ENV=production`; random per-process secret in dev (never the literal) |
| CI | infra | 14 test files, no CI; deps undeclared (`dependencies = []`). | **fixed** db00300 / 4765c91 | `test` extra (incl. jinja2) + `.github/workflows/ci.yml`, pytest py3.10-3.12, 462 green |

## Regression coverage
- `tests/test_netguard.py` — rejects metadata/loopback/RFC1918/IPv4-mapped/bad-scheme, allows public.
- `tests/test_dashboard_xss.py` — payloads escaped, benign content preserved.
- Fixed a pre-existing date-boundary flake in `test_compaction` (staggered daily ages straddled an ISO-week boundary on some run dates).

## Remaining (lower severity, hosted tier, not exposed)
- **Low** — IDOR on API-key revoke (no ownership check; UUIDs make it impractical).
- **Low** — latent SQL injection in `increment_usage` (`field` interpolated; only hardcoded values today): allowlist the column.

## Audited clean
- No real secrets in tracked files (`hosted/.env` holds only `VIGIL_DATA_DIR`/`VIGIL_APP_URL`).
- Self-hosted tier uses Jinja2 (auto-escaping); the XSS was confined to the hosted f-string renderer.
