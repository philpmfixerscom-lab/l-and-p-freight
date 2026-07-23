# L & P Freight Platform v4.4

**Load more. Deadhead less. Get home.**  
Dispatch OS for owner-operators and small bulk fleets — rates by the ton, loaded-mile tracking, cab-ready driver view.

---

## Fleet Stack

| Layer | What it is | Local URL |
|-------|------------|-----------|
| **Website** | Marketing landing + fleet entry | http://127.0.0.1:8080 |
| **Dispatch App** | Full operations command center | http://127.0.0.1:8502 |
| **Driver App** | Cab mobile UI (GPS, status, emergencies) | http://127.0.0.1:8502/?view=driver |

Production: **https://dispatch.lpfreight.com/** · **/app/** · **/driver/**

**Quick demo:** Settings → **LOAD DEMO DATA** → Dashboard → AI Intelligence → Documents.

---

## Quick Start (Local)

```powershell
cd "Projects/L & P Freight/lawson-freight-platform"
.\run-fleet.ps1
```

Opens website + dispatch together. Install both PWAs from the website or in-app prompts.

Dispatch only:

```powershell
.\run.ps1
```

Driver cabin only (same app, driver mode):

```powershell
.\run-driver.ps1
```

---

## Repository layout (single package tree)

This repo **is** the platform. There is no nested duplicate app folder.

```
.
├── app.py                 # Streamlit dispatch + Driver View entry
├── lp_helpers/            # Authoritative Python package (DB, UI, GPS, driver cabin…)
├── web/                   # Marketing site + PWA assets
├── tests/                 # pytest suite
├── scripts/               # debug + local verify
├── deploy/                # production nginx / SSL / tunnel scripts
├── run.ps1                # dispatch (creates .venv, installs deps)
├── run-fleet.ps1          # website + dispatch
└── run-driver.ps1         # driver entry URL helper
```

Import rule: **always** `from lp_helpers.…` against root `lp_helpers/`.  
Do not reintroduce a nested `lawson-freight-platform/` copy of the app.

See [ARCHITECTURE.md](ARCHITECTURE.md) for long-term structure notes.

---

## Fleet Features

| Feature | Dispatch | Driver |
|---------|----------|--------|
| Dashboard & KPIs | ✅ | — |
| Historical rates (lane / commodity / shipper) | ✅ | — |
| Leads CRM | ✅ | — |
| Load Logger + SMS auto-alert | ✅ | — |
| Load Board / BulkLoads live API (fallback intel) | ✅ | — |
| Multi-trailer / multi-driver Fleet board | ✅ | — |
| Scale ticket & condition photo upload (local paths) | ✅ | — |
| PDF export — all contracts + full audit log | ✅ | — |
| Rate quote & follow-up email/SMS templates | ✅ | — |
| GPS + Traccar live | ✅ | ✅ |
| BOL PDF generator | ✅ | — |
| Twilio SMS / SMTP alerts | ✅ | Arrival log |
| Emergency tap-to-call panel | ✅ | ✅ |
| Night driving / mobile PWA | ✅ | ✅ (cabin dark mode) |
| Status updates from cab | — | ✅ |

---

## Twilio SMS (Operational)

Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`:

```toml
[twilio]
account_sid = "ACxxxxxxxx..."
auth_token = "your_token"
from_number = "+1your_twilio_number"
dispatch_phone = "+18284678218"
auto_send_new_load = "1"
```

**Alerts tab** → Send Test Alert · Auto SMS on new load · Auto SMS on Dispatched/In Transit · rate quote / follow-up templates

### BulkLoads.com live postings

Optional partner API — without a key the Board tab uses curated NC/GA end-dump intel:

```toml
[bulkloads]
api_key = "your_partner_key"
base_url = "https://api.bulkloads.com/v1"
enabled = "1"
origin_state = "NC"
dest_state = "GA"
```

**Board tab** → **Refresh BulkLoads** syncs listings into `opportunities`.

### Photos & exports

| Path | Contents |
|------|----------|
| `./bol_photos/` | Scale tickets & condition photos (local file paths in DB) |
| `./attachments/` | BOL PDFs, contracts summary, audit log PDFs, export ZIPs |

**BOL tab** → upload photos · Export contracts PDF · Export audit log PDF · ZIP all contracts + audit.

---

## Production Deploy (Docker + HTTPS)

```powershell
# From this repo root
copy .env.example .env
# Edit .env: LP_APP_URL=https://dispatch.lpfreight.com, LP_WEB_MODE=1
.\deploy\production.ps1
```

Verify:

```powershell
.\deploy\verify-production.ps1
```

Stack: **nginx** (website + `/app/` proxy) · **Streamlit** · **certbot** · optional Cloudflare tunnel

Or Docker from repo root:

```powershell
.\deploy.ps1
```

---

## Verify Locally

```powershell
.\run-fleet.ps1          # in another terminal:
.\scripts\verify_fleet_local.ps1
```

Runs package integrity checks + pytest + health checks for website, dispatch, and driver entry.

Quick module smoke test:

```powershell
python scripts/debug_platform.py
```

---

## Data & Privacy

| Path | Contents |
|------|----------|
| `./lp_dispatch.db` | SQLite — loads, leads, SMS log, settings |
| `./attachments/` | BOL PDFs, voice memos |

Local-first. Twilio optional — credentials in `secrets.toml` only.

---

## Built for small fleets that care about cash flow

*Maximize loaded miles · Minimize deadhead · Get home.*

Tagline: **Load more. Deadhead less. Get home.**
