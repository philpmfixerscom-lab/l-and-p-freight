# Architecture — L & P Freight Platform

Long-term layout for L & P Freight. **One repo, one package tree, one source of truth.**

## Goals

- Single authoritative `lp_helpers/` package (no nested duplicates)
- Dispatch + Driver View share the same Streamlit process (`app.py`)
- Local-first SQLite; optional Twilio / Traccar / SMTP
- Scripts and Docker always run from **repo root**

## Runtime map

```
Browser
  ├─ Marketing site (web/) ── static HTTP :8080
  └─ Streamlit app.py :8502
        ├─ Dispatch tabs (Dashboard, Leads, Logger, Board, GPS, BOL, Alerts)
        └─ Driver View (?view=driver or sidebar → view_mode=driver)
              └─ lp_helpers.driver_mobile.render_driver_app
```

## Package responsibilities

| Module | Role |
|--------|------|
| `app.py` | UI shell, session state, tab wiring, safe Driver View entry |
| `lp_helpers/database.py` | Schema, settings, connections |
| `lp_helpers/driver_mobile.py` | Cab UI (status, GPS, emergency, arrival SMS) |
| `lp_helpers/emergency_alerts.py` | SOS panel + official dial list |
| `lp_helpers/traccar_live.py` | Live GPS client |
| `lp_helpers/load_board.py` | Market intel / opportunities |
| `lp_helpers/engines.py` | Rates, SMS log helpers, domain logic |
| `lp_helpers/bol_export.py` | Branded PDF BOL |
| `lp_helpers/ui_theme.py` / `ui_components.py` | Shared styling & widgets |
| `lp_helpers/mobile_web.py` | PWA / start URLs |
| `web/` | Public marketing + install manifests |

## Driver View contract

`app.safe_render_driver_view()` is the only entry used from `main()`:

1. Import `render_driver_app` from `lp_helpers.driver_mobile`
2. Pass real callbacks (`get_connection`, Traccar, SMS, emergency, exit)
3. On **any** failure, show recovery UI and return to Dispatch — never crash the process

This keeps the long-haul product resilient if a helper is temporarily broken while still using the full cabin UI when healthy.

## Navigation state (Streamlit)

**Single source of truth:** `st.session_state["active_tab"]` ∈ `TAB_KEYS`.

- Main nav uses **buttons** (`nav_btn_{key}`), not a keyed radio bound to the same state.
- `navigate_to_tab(name)` only writes `active_tab` (+ optional `nav_hint` / expander flags), then `st.rerun()`.
- **Never** assign `st.session_state[<widget_key>]` after that widget has been instantiated in the same run (StreamlitAPIException).
- Filters (`filter_*`) and form keys (`load_*`) are left intact when switching tabs.

Influenced by Streamlit session-state docs and fleet UIs (Samsara/Motive) that use explicit section nav rather than fragile tab-widget coupling.

## Multi-fleet / multi-company roadmap (phased)

| Phase | Goal | Status |
|-------|------|--------|
| **A — TenantContext** | `lp_helpers/fleet_context.py` describes current L&P tenant | Done |
| **B — Tenant resolution** | Session / login / env selects `tenant_id` | Planned |
| **C — Data scoping** | All SQL filters by `tenant_id` (leads, loads, settings) | Planned |
| **D — Multi-user RBAC** | Dispatcher vs driver vs admin roles | Planned |

**Non-breaking rule:** Phase A does not change the live single-tenant DB. Migration scripts must add nullable `tenant_id` with default `lp-freight` before enforcing NOT NULL.

## Hard rules (do not regress)

1. **Do not** recreate nested full-app copies under `lawson-freight-platform/`
2. **Do not** delete `lp_helpers/*.py` and leave only `__pycache__`
3. Launch scripts must use `$PSScriptRoot` as the platform root
4. Tests must import `lp_helpers` from the repo root on `sys.path`
5. Prefer fixing helpers over bypassing them with permanent stubs
6. **Do not** expose internal codenames (e.g. legacy "BIG E") in user-facing UI
7. Prefer `get_tenant_context()` for new branding/operator reads

## Verify

```powershell
python scripts/debug_platform.py
python -m pytest tests/ -q
.\scripts\verify_fleet_local.ps1   # with fleet stack running
```

## Data

| Path | Notes |
|------|--------|
| `lp_dispatch.db` | Authoritative operational DB at repo root |
| `backups/` | Auto DB snapshots |
| `attachments/` | BOL / media (gitignored) |
