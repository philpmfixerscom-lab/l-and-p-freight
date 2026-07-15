#!/usr/bin/env python3
"""One-shot platform diagnostics — run: python scripts/debug_platform.py"""

from __future__ import annotations

import sqlite3
import sys
import traceback
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "lp_dispatch.db"
issues: list[str] = []
ok: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        ok.append(label)
    except Exception as exc:
        issues.append(f"{label}: {exc}")
        traceback.print_exc()


def main() -> int:
    print("=== L & P Platform Debug ===\n")

    def imports():
        import app  # noqa: F401
        from lp_helpers import database, driver_mobile, traccar_live, load_board, lawson_profile

    check("Python imports", imports)

    def db_schema():
        from lp_helpers.database import init_db

        init_db()
        assert DB.exists(), f"{DB} missing after init_db"
        with closing(sqlite3.connect(DB)) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"leads", "loads", "opportunities", "sms_log", "telematics", "geofences"}
        missing = required - tables
        assert not missing, f"Missing tables: {missing}"

    check("Database init + schema", db_schema)

    def app_metrics():
        import pandas as pd
        import app

        m = app.compute_dashboard_metrics(pd.DataFrame(), pd.DataFrame())
        assert "loaded_share" in m
        fit = app.score_trailer_fit("Feldspar", 24, "")
        assert fit["level"] == "High"

    check("App helpers", app_metrics)

    def bol_pdf():
        from lp_helpers.bol_export import generate_branded_bol_pdf

        pdf = generate_branded_bol_pdf({"bol_number": "T", "shipper": "X", "commodity": "Feldspar", "weight_tons": 24})
        assert pdf.startswith(b"%PDF")

    check("BOL PDF generation", bol_pdf)

    def traccar():
        from lp_helpers.traccar_live import TraccarLive

        c = TraccarLive(get_secret=lambda _s, _k, d="": d)
        s = c.connection_status()
        assert "ok" in s

    check("Traccar client (offline OK)", traccar)

    def driver_load():
        import app
        from lp_helpers.driver_mobile import fetch_active_load

        load = fetch_active_load(app.get_connection)
        assert "bol_number" in load

    check("Driver active load fetch", driver_load)

    def deps():
        for pkg in ("streamlit", "pandas", "plotly", "reportlab", "folium", "twilio", "requests"):
            __import__(pkg)

    check("Required packages", deps)

    print(f"PASS ({len(ok)}):")
    for item in ok:
        print(f"  ✓ {item}")

    if issues:
        print(f"\nFAIL ({len(issues)}):")
        for item in issues:
            print(f"  ✗ {item}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())