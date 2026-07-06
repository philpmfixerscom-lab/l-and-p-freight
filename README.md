# L & P Dispatch v3.0 — Freight OS

**Local-first freight intelligence platform for Phillip & Lawson (L & P Dispatch)**  
Spruce Pine NC · 39ft / 24-ton lined end-dump · Spruce Pine → Central Georgia lane

---

## Vision

L & P Dispatch Freight OS is a **premium, offline-capable command center** built for a single-truck operation that needs to **look and perform like 2026 freight tech** — without giving up data ownership. Every record lives on your machine. AI is **transparent and rule-based** (no black-box ML). Phillip and Lawson make every final call.

**Sell it in 60 seconds:** Settings → **LOAD DEMO DATA** → Dashboard → AI Intelligence → Documents.

---

## Quick Start

```powershell
cd "Projects/L & P Freight"
.\run.ps1
```

Open **http://localhost:8501**

### Requirements

- Python 3.11–3.13
- `streamlit`, `pandas`, `openpyxl`, `reportlab`, `twilio` (optional)

---

## Killer Features to Demo

| Feature | Where | What to show |
|--------|--------|--------------|
| **Demo Mode** | Settings → LOAD DEMO DATA | 12 loads, fuel, maintenance, arrivals — instant wow |
| **Live Map Sim** | Dashboard | Animated truck on Spruce Pine → GA corridor |
| **AI Load Score** | AI Intelligence | Score 0–100 with profitability / deadhead / trailer / history breakdown |
| **Rate Simulator** | AI Intelligence → Simulator | Revenue, fuel est., margin % — transparent math |
| **Document OCR** | Documents | Camera or upload → simulated extraction → CREATE LOAD |
| **Voice + AI Summary** | Load Logger / Leads & Calls | Record + text → structured fields + suggested actions |
| **Smart Arrival** | Geofence Dispatch | Haversine zones → pre-filled status, notes, SMS draft |
| **SMS Generator** | SMS Alerts | Arrival / load update / departure templates + optional Twilio |
| **Branded Outputs** | Reports | BOL PDF · performance report · invoice preview |
| **Predictive Insights** | Insights | Lane trends, maintenance alerts, Trimac backhaul ROI |

---

## Design Principles

- **Glassmorphism / cyber-trucking** aesthetic — dark sidebar, orange CTAs, pulsing traffic lights
- **Thumb-zone mobile** — ≥52px (56px on mobile) touch targets, night-driving mode
- **Traffic-light status** — green / amber / red on KPIs, scores, and insights
- **ROI inside the app** — e.g. *"This recommendation saves X deadhead miles"*
- **L & P Dispatch branding** everywhere — BOLs, invoices, reports, SMS

---

## Data & Privacy

| Path | Contents |
|------|----------|
| `./lp_dispatch.db` | All SQLite records (loads, leads, geofences, fuel, etc.) |
| `./attachments/` | Voice memos, BOL PDFs, document scans |

No cloud sync. Twilio is **optional** — credentials stored only in local `app_settings`.

---

## Owner Operations

- **Phillip / Lawson role** — Settings → Operating as (role-aware dashboard header)
- **Night Driving** — sidebar toggle or Settings
- **Bulk import** — Load Logger → CSV/XLSX → VALIDATE → IMPORT
- **Nuclear Delete** — Settings → type `DELETE L&P` (irreversible)

---

## AI Disclaimer

All "AI" features are **transparent rule-based engines** — load scoring, OCR simulation, voice summary, and suggestions show their logic. Not legal, financial, or safety advice. Replace OCR placeholder with Tesseract or a cloud API when ready.

---

## Built for L & P Dispatch

*Maximize loaded miles · Minimize deadhead · Automate daily ops.*

Primary lane: **Spruce Pine NC → Central Georgia (Kohler area)**  
Hot leads: Sibelco · Covia · K-T Feldspar · Trimac