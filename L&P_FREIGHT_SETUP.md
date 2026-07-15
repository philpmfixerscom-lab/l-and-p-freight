# L & P Dispatch — Freight OS Setup

## Run (Windows PowerShell)

```powershell
cd "Projects/L & P Freight/lawson-freight-platform"
.\run.ps1
```

Opens **http://127.0.0.1:8502** — creates `.venv`, installs deps, starts Streamlit.

Fleet (website + dispatch):

```powershell
.\run-fleet.ps1
```

Driver cabin: **http://127.0.0.1:8502/?view=driver** or `.\run-driver.ps1`

## First-Time Demo (60 seconds)

1. Open app → **Settings** → **LOAD DEMO DATA**
2. **Dashboard** → live map + ROI KPIs
3. **AI Intelligence** → score a load
4. **Reports** → download branded BOL PDF

## Data (local only)

| File | Purpose |
|------|---------|
| `lp_dispatch.db` | All operational SQLite records (repo root) |
| `attachments/` | Voice memos, BOLs, document scans |
| `lawson_freight.db` / `lp_freight.db` | Legacy — auto-merged on first run |

## Manual Run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

## Package layout

Single tree only — `app.py` + `lp_helpers/` at repo root.  
See **ARCHITECTURE.md** and **README.md**.
