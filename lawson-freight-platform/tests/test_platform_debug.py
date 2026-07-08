"""Platform smoke tests — DB, helpers, Lawson profile, no Streamlit UI."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_lawson_profile_imports():
    from lp_helpers.lawson_profile import (
        BIG_E_MODE,
        LAWSON_SEED_LEADS,
        LAWSON_SIM_ROUTE,
        PLATFORM_TITLE,
    )

    assert BIG_E_MODE is True
    assert len(LAWSON_SEED_LEADS) >= 4
    assert len(LAWSON_SIM_ROUTE) >= 2
    assert "BIG E" in PLATFORM_TITLE


def test_database_init_and_schema(tmp_path, monkeypatch):
    db = tmp_path / "test_dispatch.db"
    monkeypatch.setenv("LP_DATA_DIR", str(tmp_path))

    from lp_helpers import database as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", db)
    dbmod.init_db()

    assert db.exists()
    with closing(sqlite3.connect(db)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for required in ("leads", "loads", "opportunities", "sms_log", "telematics"):
        assert required in tables


def test_app_helper_functions():
    import app as platform

    assert platform.APP_VERSION
    assert len(platform.TAB_KEYS) == len(platform.TAB_LABELS)
    assert "Board" in platform.TAB_KEYS

    fit = platform.score_trailer_fit("Feldspar", 24.0, "")
    assert fit["level"] == "High"

    rate, rev = platform.calculate_rate(24.0, 285.0, 285.0, "Feldspar")
    assert rate > 0 and rev > 0

    metrics = platform.compute_dashboard_metrics(
        pd.DataFrame([{"status": "Hot", "company": "Sibelco"}]),
        pd.DataFrame(
            [
                {
                    "total_revenue": 1152.0,
                    "weight_tons": 24.0,
                    "rate_per_ton": 48.0,
                    "miles": 285.0,
                    "loaded_miles": 285.0,
                    "deadhead_miles": 0.0,
                    "status": "In Transit",
                }
            ]
        ),
    )
    assert metrics["loads_logged"] == 1
    assert metrics["loaded_share"] == 1.0


def test_traccar_live_offline_graceful():
    from lp_helpers.traccar_live import TraccarLive

    client = TraccarLive(get_secret=lambda s, k, d="": d)
    status = client.connection_status()
    assert "ok" in status
    assert client.get_live_fix() is None or isinstance(client.get_live_fix(), dict)


def test_bulkloads_upsert_no_duplicates(tmp_path, monkeypatch):
    db = tmp_path / "test_board.db"
    monkeypatch.setenv("LP_DATA_DIR", str(tmp_path))
    from lp_helpers import database as dbmod
    from lp_helpers.load_board import upsert_market_intel

    monkeypatch.setattr(dbmod, "DB_PATH", db)
    dbmod.init_db()
    with closing(sqlite3.connect(db)) as conn:
        assert upsert_market_intel(
            conn,
            lane="Spruce Pine, NC → Kohler, GA",
            commodity="Feldspar",
            rate="$48/ton",
            contact="Broker",
        )
        assert not upsert_market_intel(
            conn,
            lane="Spruce Pine, NC → Kohler, GA",
            commodity="Feldspar",
            rate="$50/ton",
            contact="Broker",
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert n == 1


def test_bol_pdf_generation():
    from lp_helpers.bol_export import generate_branded_bol_pdf

    load = {
        "bol_number": "LP-TEST-001",
        "shipper": "Sibelco",
        "commodity": "Feldspar",
        "weight_tons": 24,
        "origin": "Spruce Pine, NC",
        "destination": "Central Georgia (Kohler area)",
        "rate_per_ton": 48.0,
        "total_revenue": 1152.0,
        "pickup_date": "2026-07-08",
        "status": "Logged",
    }
    pdf = generate_branded_bol_pdf(load)
    assert pdf[:4] == b"%PDF"