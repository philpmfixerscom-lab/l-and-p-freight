"""Tests for BulkLoads API, templates, rate analytics, fleet, photos, audit export."""

from __future__ import annotations

import sys
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_bulkloads_fallback_without_key():
    from lp_helpers.bulkloads_api import fetch_live_postings, is_live_configured

    assert is_live_configured() is False or isinstance(is_live_configured(), bool)
    result = fetch_live_postings()
    assert "listings" in result
    assert len(result["listings"]) >= 1
    assert result["source"] in ("fallback", "api")
    row = result["listings"][0]
    assert "lane" in row and "commodity" in row and "rate" in row


def test_rate_quote_templates():
    from lp_helpers.followup_templates import (
        FOLLOWUP_TEMPLATES,
        RATE_QUOTE_KEYS,
        build_followup_message,
        parse_email_template,
    )

    assert "rate_quote_sms" in FOLLOWUP_TEMPLATES
    assert "rate_quote_email" in FOLLOWUP_TEMPLATES
    assert len(RATE_QUOTE_KEYS) >= 4
    sms = build_followup_message(
        "rate_quote_sms",
        {
            "company": "Sibelco",
            "commodity": "Feldspar",
            "weight_tons": 24,
            "rate_per_ton": 50.0,
            "total_revenue": 1200.0,
        },
    )
    assert "RATE QUOTE" in sms
    assert "Sibelco" in sms
    email = build_followup_message("rate_quote_email", {"contact_name": "Dispatch"})
    subject, body = parse_email_template(email)
    assert "Rate Quote" in subject or "L & P" in subject
    assert "Dispatch" in body or "Hi" in body


def test_historical_rate_analytics():
    from lp_helpers.analytics_dashboard import compute_historical_rates

    df = pd.DataFrame(
        [
            {
                "origin": "Spruce Pine, NC",
                "destination": "Central Georgia",
                "commodity": "Feldspar",
                "shipper": "Sibelco",
                "rate_per_ton": 48.0,
                "total_revenue": 1152.0,
                "weight_tons": 24.0,
                "loaded_miles": 285.0,
                "miles": 300.0,
                "status": "Completed",
                "pickup_date": "2026-06-01",
            },
            {
                "origin": "Spruce Pine, NC",
                "destination": "Central Georgia",
                "commodity": "Feldspar",
                "shipper": "Covia",
                "rate_per_ton": 52.0,
                "total_revenue": 1248.0,
                "weight_tons": 24.0,
                "loaded_miles": 285.0,
                "miles": 300.0,
                "status": "Completed",
                "pickup_date": "2026-07-01",
            },
        ]
    )
    hist = compute_historical_rates(df)
    assert not hist["by_lane"].empty
    assert not hist["by_commodity"].empty
    assert len(hist["by_shipper"]) == 2
    assert "avg_rate_per_ton" in hist["by_lane"].columns


def test_fleet_board_build():
    from lp_helpers.fleet_view import build_fleet_board

    assets = pd.DataFrame(
        [
            {
                "id": 1,
                "asset_type": "Truck+Trailer",
                "name": "Unit 1",
                "description": "Primary",
                "driver_name": "",
            },
            {
                "id": 2,
                "asset_type": "Driver",
                "name": "Phillip Vencill",
                "description": "Owner",
                "driver_name": "Phillip Vencill",
            },
        ]
    )
    loads = pd.DataFrame(
        [
            {
                "id": 10,
                "bol_number": "LP-TEST",
                "shipper": "Sibelco",
                "commodity": "Feldspar",
                "origin": "SP",
                "destination": "GA",
                "status": "In Transit",
                "asset_id": 1,
                "driver_name": "Phillip Vencill",
                "trailer_name": "Unit 1",
            }
        ]
    )
    cards = build_fleet_board(assets, loads)
    assert len(cards) == 2
    unit = next(c for c in cards if c["id"] == 1)
    assert unit["active_loads"] == 1
    assert "Feldspar" in unit["load_summary"]


def test_photo_save_and_path(tmp_path, monkeypatch):
    from lp_helpers import load_photos

    monkeypatch.setattr(load_photos, "PHOTOS_DIR", tmp_path / "bol_photos")
    # Use in-memory path for DB would be complex; just ensure save writes file via save with mocked get_conn
    # File write path only:
    load_photos.ensure_photos_dir()
    assert (tmp_path / "bol_photos").is_dir()

    dest = load_photos.PHOTOS_DIR / "test.jpg"
    dest.write_bytes(b"\xff\xd8\xff fakejpeg")
    resolved = load_photos.resolve_photo_path(str(dest))
    assert resolved.is_file()


def test_audit_pdf_and_contracts():
    from lp_helpers.audit_log import (
        generate_audit_log_pdf,
        generate_contracts_bundle_pdf,
        generate_all_contracts_zip,
    )

    loads = pd.DataFrame(
        [
            {
                "id": 1,
                "bol_number": "LP-TEST-001",
                "shipper": "Sibelco",
                "commodity": "Feldspar",
                "weight_tons": 24,
                "origin": "Spruce Pine, NC",
                "destination": "Central GA",
                "rate_per_ton": 48,
                "total_revenue": 1152,
                "status": "Logged",
                "loaded_miles": 285,
                "deadhead_miles": 40,
                "miles": 325,
                "notes": "Test",
            }
        ]
    )
    contracts = generate_contracts_bundle_pdf(loads)
    assert contracts[:4] == b"%PDF"
    audit = generate_audit_log_pdf(pd.DataFrame())
    assert audit[:4] == b"%PDF"

    def fake_bol(load: dict) -> bytes:
        return b"%PDF-1.4 fake bol"

    z = generate_all_contracts_zip(loads, fake_bol, include_audit=True)
    assert len(z) > 100
    assert z[:2] == b"PK"


def test_required_new_modules_exist():
    helpers = ROOT / "lp_helpers"
    for name in (
        "bulkloads_api.py",
        "fleet_view.py",
        "load_photos.py",
        "audit_log.py",
        "followup_templates.py",
        "analytics_dashboard.py",
        "inventory.py",
    ):
        assert (helpers / name).is_file(), name


def test_inventory_insert_and_recalculate(tmp_path, monkeypatch):
    from lp_helpers.database import get_conn, init_db
    from lp_helpers.inventory import (
        get_lead_inventory_latest,
        insert_inventory_estimate,
        level_to_tons,
        recalculate_days_of_supply,
        days_of_supply_color,
        render_days_of_supply,
    )

    db_path = tmp_path / "test_inv.db"
    monkeypatch.setattr("lp_helpers.database.DB_PATH", db_path)
    init_db()

    with closing(get_conn()) as conn:
        cur = conn.execute(
            "INSERT INTO leads (company, status, avg_weekly_tons, bin_capacity_tons) VALUES (?,?,?,?)",
            ("Test Shipper", "Hot", 10.0, 24.0),
        )
        lead_id = int(cur.lastrowid)

        insert_inventory_estimate(
            conn,
            lead_id=lead_id,
            load_id=None,
            commodity="Feldspar",
            estimated_level="3/4",
            estimated_tons=18.0,
            photo_paths=[],
            driver_notes="scale: 18t",
            estimated_by="Phillip",
        )
        days = recalculate_days_of_supply(conn, lead_id)
        assert days is not None
        assert abs(days - 12.6) < 0.2

        latest = get_lead_inventory_latest(conn, lead_id)
        assert latest is not None
        assert latest["level"] == "3/4"
        assert latest["tons_est"] == 18.0

        # lead last_estimate_* + days_of_supply_est updated
        lead_row = conn.execute(
            "SELECT last_estimate_level, last_estimate_tons, days_of_supply_est FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        assert lead_row["last_estimate_level"] == "3/4"
        assert float(lead_row["last_estimate_tons"] or 0) == 18.0
        assert lead_row["days_of_supply_est"] is not None
        assert abs(float(lead_row["days_of_supply_est"]) - 12.6) < 0.2

    assert level_to_tons("Empty", 24.0) == 0.0
    assert abs(level_to_tons("3/4", 24.0) - 18.0) < 0.01
    assert abs(level_to_tons("Full", 24.0) - 24.0) < 0.01
    # Driver-facing supply labels
    from lp_helpers.inventory import BIN_LEVEL_OPTIONS

    assert len(BIN_LEVEL_OPTIONS) == 5
    assert level_to_tons("Empty / Near Empty", 24.0) == 0.0
    assert abs(level_to_tons("Full / Overstocked", 24.0) - 24.0) < 0.01
    assert abs(level_to_tons("Medium (3-7 days)", 24.0) - 10.8) < 0.01
    assert days_of_supply_color(None) == "#94a3b8"
    assert days_of_supply_color(15.0) == "#4ade80"
    assert days_of_supply_color(10.0) == "#fbbf24"
    assert days_of_supply_color(3.0) == "#f87171"
    assert render_days_of_supply(None) == "—"
    assert "#4ade80" in render_days_of_supply(15.0)
    assert "15 days" in render_days_of_supply(15.0)


def test_inventory_recalculate_zero_avg(tmp_path, monkeypatch):
    from lp_helpers.database import get_conn, init_db
    from lp_helpers.inventory import recalculate_days_of_supply

    db_path = tmp_path / "test_inv_zero.db"
    monkeypatch.setattr("lp_helpers.database.DB_PATH", db_path)
    init_db()

    with closing(get_conn()) as conn:
        cur = conn.execute(
            "INSERT INTO leads (company, status, avg_weekly_tons) VALUES (?,?,?)",
            ("Zero Shipper", "Active", 0.0),
        )
        lead_id = int(cur.lastrowid)
        days = recalculate_days_of_supply(conn, lead_id)
        assert days is None


def test_inventory_dual_schema_legacy_not_null(tmp_path, monkeypatch):
    """Production DBs may have estimated_level NOT NULL — insert must dual-write."""
    import sqlite3

    from lp_helpers.inventory import (
        ensure_inventory_estimate_columns,
        get_lead_inventory_latest,
        insert_inventory_estimate,
        inventory_estimates_select_sql,
        recalculate_days_of_supply,
    )

    db_path = tmp_path / "legacy_inv.db"
    monkeypatch.setattr("lp_helpers.database.DB_PATH", db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            avg_weekly_tons REAL,
            bin_capacity_tons REAL,
            last_estimate_level TEXT,
            last_estimate_date TEXT,
            last_estimate_tons REAL,
            days_of_supply_est REAL
        );
        CREATE TABLE inventory_estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER,
            load_id INTEGER,
            commodity TEXT,
            estimated_level TEXT NOT NULL,
            estimated_tons REAL NOT NULL DEFAULT 0.0,
            photo_paths TEXT,
            driver_notes TEXT,
            estimated_by TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    cur = conn.execute(
        "INSERT INTO leads (company, avg_weekly_tons, bin_capacity_tons) VALUES (?,?,?)",
        ("Legacy Shipper", 14.0, 24.0),
    )
    lead_id = int(cur.lastrowid)
    conn.commit()

    cols = ensure_inventory_estimate_columns(conn)
    assert "level" in cols and "estimated_level" in cols

    eid = insert_inventory_estimate(
        conn,
        lead_id=lead_id,
        load_id=None,
        commodity="Feldspar",
        estimated_level="Medium (3-7 days)",
        estimated_tons=10.8,
        photo_paths=["a.jpg"],
        driver_notes="silo check",
        estimated_by="Driver",
    )
    assert eid >= 1
    days = recalculate_days_of_supply(conn, lead_id)
    assert days is not None
    # 10.8 / 14 * 7 ≈ 5.4
    assert abs(days - 5.4) < 0.2

    row = conn.execute(
        "SELECT estimated_level, level, estimated_tons, tons_est, driver_notes, notes FROM inventory_estimates WHERE id=?",
        (eid,),
    ).fetchone()
    assert row["estimated_level"] == "Medium (3-7 days)"
    assert row["level"] == "Medium (3-7 days)"
    assert float(row["estimated_tons"]) == 10.8
    assert float(row["tons_est"]) == 10.8
    assert row["driver_notes"] == "silo check"
    assert row["notes"] == "silo check"

    latest = get_lead_inventory_latest(conn, lead_id)
    assert latest is not None
    assert latest["level"] == "Medium (3-7 days)"
    assert latest["tons_est"] == 10.8

    sql = inventory_estimates_select_sql(cols, where_lead=True)
    import pandas as pd

    df = pd.read_sql_query(sql, conn, params=(lead_id,))
    assert not df.empty
    assert df.iloc[0]["level"] == "Medium (3-7 days)"
    assert df.iloc[0]["shipper"] == "Legacy Shipper"
    conn.close()

