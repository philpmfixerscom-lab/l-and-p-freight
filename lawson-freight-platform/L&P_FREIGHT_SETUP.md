# L & P Dispatch v3.0 — Freight OS Setup

## Run (Windows PowerShell)

```powershell
cd "Projects/L & P Freight"
.\run.ps1
```

Opens **http://localhost:8501** — creates `.venv`, installs deps, starts Streamlit.

Port busy? Edit `run.ps1` → change `--server.port 8501` to `8502`.

## First-Time Demo (60 seconds)

1. Open app → **Settings** → **LOAD DEMO DATA**
2. **Dashboard** → live map + ROI KPIs
3. **AI Intelligence** → score a load
4. **Reports** → download branded BOL PDF

## Data (local only)

| File | Purpose |
|------|---------|
| `lp_dispatch.db` | All operational SQLite records |
| `attachments/` | Voice memos, BOLs, document scans |
| `lawson_freight.db` / `lp_freight.db` | Legacy — auto-merged on first run |

## Manual Run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Full docs

See **README.md** for vision, feature map, and privacy notes.