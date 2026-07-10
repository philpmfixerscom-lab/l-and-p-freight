# L & P Freight Platform — Codebase Review

**Date:** 2026-07-06  
**Repo:** https://github.com/philpmfixerscom-lab/l-and-p-freight  
**Status:** In progress, Phase 1-4 MVP committed, 22/22 tests passing

---

## Consolidation Update — 2026-07-10

Single-app consolidation completed. `app.py` is now the one canonical entrypoint
(`run.ps1`), running on the single schema owned by `lp_helpers/database.py`.

- **Single schema source of truth:** `app.py` now calls `database.init_db()` at
  startup instead of its own partial `init_billing_schema()`. It no longer crashes
  on a fresh `lp_dispatch.db` (previously `leads`/`loads` were never created).
- **Schema reconciliation:** `app.py` now uses the canonical columns
  (`leads.company`, `loads.pickup_date`, `loads.deadhead_miles`). The Dashboard and
  Leads tabs previously referenced non-existent columns (`leads.name`,
  `next_followup_date`, `followup_type`) — those follow-up fields are now real
  columns on `leads` (added in `database.py` schema + idempotent migration).
- **PDF BOL restored:** the BOL tab now emits a proper PDF (was plain `.txt`).
- **Retired duplicates:** deleted the standalone `lawson-freight-platform/` build,
  `run_lawson.ps1`, and the duplicate nested `L&P_Freight/` notes folder.
- **Verified:** cold-start smoke test (Streamlit `AppTest`, all tabs, fresh DB) +
  full `pytest` suite (22 passing).
- **Still open:** `lp_helpers/pages.py` (the richer README-documented v3.0 UI:
  Demo Data / AI Intelligence / Reports) remains in the tree but is **not wired**
  to an entrypoint — candidate for a future merge into `app.py`.

---

## Feature Additions — 2026-07-10 (Lawson's asks)

Implemented on top of the consolidated single app. Test count: **41 passing**.

- **Pay for actual miles driven** (`lp_helpers/pay_engine.py`, tested): drivers are
  ALWAYS paid for the miles they actually drove. If Google shorts the lane 30 mi or
  the driver runs an alternate route, pay follows the real miles. Google/planned is
  reference only; deviations beyond ±10% are *flagged for review* but never reduce
  pay. The settlement tab now shows an explicit dollar-impact decision.
- **Customer real-time billing on load acceptance**: `loads.accepted_at` added
  (schema + migration). A new "Driver Load Acceptance & Status" control flips a load
  to Accepted/In Transit/Delivered; the moment a driver accepts, the Customer Portal
  shows "BILLING LIVE", a live-billing KPI, and a downloadable live invoice.
- **PO multi-load scheduling/tracking**: already present; now synced to load status.
- **ELD / hardware ingest** (`routing_editor.ingest_eld_miles`, `create_eld_webhook`,
  tested): in-cab hardware miles flow into route actuals → driver pay. Includes a
  vendor-agnostic webhook ingress and a "Push actuals from ELD device" button.
- **Truck/trailer/route categorization**: covered by existing asset profiles
  (Truck+Trailer / Truck / Trailer, per-mile loaded/empty rates) + route/settlement.
- **Brokerage build tracker**: `BROKERAGE_CHECKLIST.md` (LLC/EIN/USDOT/MC/insurance/
  BMC-84 bond + market intel from Lawson's notes).

**New tests:** `tests/test_pay_engine.py` (13), `tests/test_eld_ingest.py` (6).

---

## Overall Architecture

```
L & P Freight/
├── app.py                     # Main Streamlit dispatch app (956 lines)
├── lp_helpers/
│   ├── __init__.py
│   ├── database.py            # SQLite persistence (1093 lines)
│   ├── engines.py             # Rule-based AI/rule engines (1289 lines)
│   ├── pages.py               # Page render functions (1463 lines)
│   ├── ui_theme.py            # CSS theme system
│   ├── ui_components.py       # Reusable widgets
│   ├── analytics_dashboard.py # Financial/revenue charts
│   ├── bol_export.py          # BOL PDF generation
│   ├── followup_templates.py  # SMS/email sequences
│   ├── load_board.py          # Load board integration
│   └── mobile_web.py          # Mobile web wrapper
├── portal.py                  # Customer portal (customers, POs, po_loads)
├── routing_editor.py          # Routes table, variance analysis, fairness engine
├── eld_integration.py         # ELDClient facade + StubEldProvider
├── eld_api_stubs.py           # Samsara, Motive, Geotab vendor stubs
├── mobile_app.py              # Mobile driver app (bottom nav, cabin mode)
├── tests/
│   ├── test_routing.py         # 17 passing (variance, pay calc, route lifecycle)
│   └── test_portal.py          # 5 passing (customers, POs, summary)
├── deploy/                    # Docker/nginx/Cloudflare deployment configs
├── web/                       # Static marketing site bundle
└── eld_mobile/index.html      # Driver PWA stub
```

---

## Strengths

| Area | Notes |
|------|-------|
| **Local-first design** | SQLite backend, no cloud subscription, data ownership preserved |
| **Modular helpers** | `lp_helpers/` package separates DB, engines, pages, UI — good pattern |
| **Rule-based AI** | Transparent scoring (0-100), no black-box ML — matches owner-op ethos |
| **Comprehensive feature set** | Leads, loads, deadhead tracking, settlements, customer portal, ELD stub |
| **Variance fairness** | Route variance analysis with dispatcher tolerance threshold (±10%) |
| **Testing** | 22 passing tests covering routing math, pay calc, portal CRUD |
| **Deployment ready** | docker-compose, Dockerfile, nginx + Cloudflare tunnel configs |
| **Documentation** | README, ROADMAP, DESIGN_REVIEW, L&P_FREIGHT_SETUP |
| **ELD vendor-agnostic** | Protocol-based facade allows swapping Samsara/Motive/Geotab |

---

## Issues / Gaps

### Critical

1. **Multiple DB files** — `lawson_freight.db`, `lp_freight.db`, `l_and_p_freight.db`, `lp_dispatch.db` suggest schema thrash. Need migration docs.
2. **_decompiled/** — Decompiled bytecode from older compiled `app.py` is tracked. Should be in .gitignore.
3. **mcps/** — External vendor JSON schemas (Grok, Notion, Vercel) are tracked. Not app source.
4. **app.py + lp_helpers/pages.py duplicate** — App has two parallel UI implementations. The `lp_helpers/pages.py` (1463 lines) appears unused by current `app.py` (956 lines).
5. **requirements.txt** missing deps — `fpdf2` is used in `app.py` but `requirements.txt` has `reportlab` (unused) and no `fpdf2`.

### Medium

6. **No pyproject.toml / setup.py** — Not pip-installable. No package metadata.
7. **terminals/** directory tracked — Terminal output artifacts.
8. **.env not gitignored** — Can expose Twilio credentials if committed.
9. **app_v3_recovered.py* files** — Recovery artifacts tracked in git.
10. **Mobile app standalone** — `mobile_app.py` has `st.set_page_config` which conflicts if imported from `app.py`. Needs isolated entrypoint.

### Low

11. **No CI/CD** — No GitHub Actions for tests / lint.
12. **No type checking** — Mypy strict not enforced.
13. **SQL injection risk** — Some f-string SQL in `database.py` (e.g., `f"SELECT ... WHERE po_id IN ({placeholders})"`).
14. **Hardcoded credentials** — `eld_api_stubs.py` has GitHub PAT in test file (masked here).

---

## Recommended Immediate Fixes

1. Add `mcps/`, `_decompiled/`, `terminals/`, `.env`, `*.pdf`, `deploy/cloudflared.exe` to `.gitignore`
2. Remove `mcps/`, `_decompiled/`, `terminals/` from git tracking
3. Reconcile `app.py` (956 lines) vs `lp_helpers/pages.py` (1463 lines) — pick one entrypoint
4. Update `requirements.txt` to match actual imports: `fpdf2`, `streamlit`, `pandas`, `plotly`, `twilio`, `openpyxl`, `streamlit-folium` (if maps)
5. Add `pyproject.toml` with `[project]` metadata
6. Add GitHub Actions: `pytest` on push, `ruff` lint check

---

## Feature Completeness

| Module | Status | Notes |
|--------|--------|-------|
| **Leads/CRM** | ✅ Complete | Follow-up sequences, status tracking, demo seed data |
| **Load Logger** | ✅ Complete | Deadhead split, commodity selector, BOL generation |
| **Rate Calculator** | ✅ Complete | Deadhead-adjusted revenue, driver pay preview |
| **AI Engines** | ✅ Complete | Load scoring, OCR sim, voice summary, geofence, insights |
| **Geofence** | ✅ Complete | Haversine zones, proximity fill, smart arrival prefill |
| **BOL/PDF** | ✅ Complete | FPDF-based BOL, invoice preview, performance report |
| **Billing/Driver Pay** | ✅ Complete | Assets, settlements, PDF statements, variance flags |
| **Routing** | ✅ Complete | Waypoints, Google vs actual, variance report |
| **Customer Portal** | ✅ Complete | Customers, POs, bulk load scheduling, role-based view |
| **ELD Integration** | ✅ Stub | Facade complete, vendor stubs raise NotImplementedError |
| **Mobile App** | ✅ Prototype | Bottom nav, cabin mode, HOS clocks, 52px touch targets |
| **SMS** | ✅ Stub | Twilio optional, template generator |
| **Deploy** | ✅ Complete | Docker, nginx, Cloudflare tunnel, verify script |

---

## Test Coverage

- **22 tests total, 22 passing**
- `tests/test_routing.py` — 17 tests: variance analysis, driver pay, route validation, lifecycle, fairness
- `tests/test_portal.py` — 5 tests: seed customers, PO CRUD, status transitions, summary, billing visibility

**Not covered:** UI rendering, ELD vendor stubs, BOL PDF generation, geofence logic, bulk import edge cases.
