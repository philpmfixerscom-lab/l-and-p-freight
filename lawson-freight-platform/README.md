# L & P Dispatch — Lawson Freight Platform v4.4

**Fleet-ready dispatch OS for Phillip & Lawson**  
Spruce Pine NC · 39ft / 24-ton end-dump · Spruce Pine → Central Georgia lane

---

## Fleet Stack

| Layer | What it is | Local URL |
|-------|------------|-----------|
| **Website** | Marketing landing + fleet entry | http://127.0.0.1:8080 |
| **Dispatch App** | Full operations command center | http://127.0.0.1:8502 |
| **Driver App** | Cab mobile UI (GPS, status, emergencies) | http://127.0.0.1:8502/?view=driver |

Production: **https://dispatch.lpfreight.com/** · **/app/** · **/driver/**

---

## Quick Start (Local)

```powershell
cd "Projects/L & P Freight"
.\run-fleet.ps1
```

Opens website + dispatch together. Install both PWAs from the website or in-app prompts.

Dispatch only:

```powershell
.\run.ps1
```

---

## Fleet Features

| Feature | Dispatch | Driver |
|---------|----------|--------|
| Dashboard & KPIs | ✅ | — |
| Leads CRM | ✅ | — |
| Load Logger + SMS auto-alert | ✅ | — |
| Load Board / BulkLoads intel | ✅ | — |
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

**Alerts tab** → Send Test Alert · Auto SMS on new load · Auto SMS on Dispatched/In Transit

---

## Production Deploy (Docker + HTTPS)

```powershell
cd lawson-freight-platform
copy .env.example .env
# Edit .env: LP_APP_URL=https://dispatch.lpfreight.com, LP_WEB_MODE=1
.\deploy\production.ps1
```

Verify:

```powershell
.\deploy\verify-production.ps1
```

Stack: **nginx** (website + `/app/` proxy) · **Streamlit** · **certbot** · optional Cloudflare tunnel

---

## Verify Locally

```powershell
.\run-fleet.ps1          # in another terminal:
.\scripts\verify_fleet_local.ps1
```

Runs pytest + health checks for website, dispatch, and driver entry.

---

## Data & Privacy

| Path | Contents |
|------|----------|
| `./lp_dispatch.db` | SQLite — loads, leads, SMS log, settings |
| `./attachments/` | BOL PDFs, voice memos |

Local-first. Twilio optional — credentials in `secrets.toml` only.

---

## Built for L & P Dispatch

*Maximize loaded miles · Minimize deadhead · Automate daily ops.*

Hot leads: Sibelco · Covia · K-T Feldspar · Trimac