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
- Filter widgets bind **directly** to `filter_leads_*` / `filter_loads_*` (no dual `*_ui` keys).
- Load Logger prefill is durable: `load_prefill` + `_load_prefill_pending` until Logger applies it.
- Deadhead empty location: `dh_empty_at` (chips + optional custom text); survives tab switches.
- Driver exit only clears `view_mode` → `dispatch` (preserves `active_tab` and drafts).

### Session state map (app)

| Key | Role |
|-----|------|
| `active_tab` | Dispatch section |
| `view_mode` | `dispatch` \| `driver` |
| `night_mode` | Theme (Driver View reads it) |
| `filter_*` | Leads/loads list filters |
| `load_*` | Logger draft fields |
| `dh_*` | Deadhead empty location + score inputs |
| `load_prefill` / `_load_prefill_pending` | Cross-tab logger prefill |

Influenced by Streamlit session-state docs and fleet UIs (Samsara/Motive) that use explicit section nav rather than fragile tab-widget coupling.

## Multi-fleet / multi-company roadmap (phased)

| Phase | Goal | Status |
|-------|------|--------|
| **A — TenantContext** | `fleet_context.py` current L&P tenant | **Done** |
| **B — Schema + session** | `tenancy.py` migrations; `tenant_id` on business tables; session bind | **Done (foundation)** |
| **C — Repos enforce scope** | `repositories/loads.py`, `leads.py` filter/insert by tenant | **Done (loads/leads)** |
| **D — Multi-user RBAC** | `authz.py` roles; login UI | Foundation only (solo = `owner_driver`) |
| **E — Integration / AI ports** | `integrations/telematics_port.py`, `ai/ports.py` | Foundation shipped |

**Non-breaking rule:** Phase B backfills `tenant_id='lp-freight'`; UX unchanged for single-truck deploys.

### New modules (Phase B+)

| Module | Purpose |
|--------|---------|
| `lp_helpers/tenancy.py` | Default tenant id, schema ensure, `current_tenant_id()` |
| `lp_helpers/authz.py` | RBAC principal + `can`/`require` |
| `lp_helpers/repositories/` | Tenant-scoped SQL for loads & leads |
| `lp_helpers/integrations/telematics_port.py` | Traccar / Manual adapters behind a port |
| `lp_helpers/ai/ports.py` | RateOptimizer / LoadMatcher rules v1 |

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
