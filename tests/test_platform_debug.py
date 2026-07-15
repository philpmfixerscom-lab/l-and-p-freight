"""Platform smoke tests — DB, helpers, Lawson profile, no Streamlit UI."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Authoritative package modules — must exist as .py sources (not pycache-only).
REQUIRED_LP_HELPERS = (
    "__init__.py",
    "analytics_dashboard.py",
    "bol_export.py",
    "database.py",
    "driver_mobile.py",
    "emergency_alerts.py",
    "engines.py",
    "followup_templates.py",
    "lawson_profile.py",
    "load_board.py",
    "mobile_web.py",
    "pages.py",
    "traccar_live.py",
    "ui_components.py",
    "ui_theme.py",
)


def test_single_package_tree_and_helper_sources():
    """Guard against nested-duplicate regressions and missing lp_helpers sources."""
    helpers = ROOT / "lp_helpers"
    assert helpers.is_dir(), "lp_helpers/ package missing at repo root"

    missing = [name for name in REQUIRED_LP_HELPERS if not (helpers / name).is_file()]
    assert not missing, f"Missing lp_helpers sources: {missing}"

    nested_app = ROOT / "lawson-freight-platform" / "app.py"
    assert not nested_app.exists(), (
        "Nested lawson-freight-platform/app.py found — keep a single package tree at repo root"
    )

    from lp_helpers.driver_mobile import fetch_active_load, render_driver_app

    assert callable(fetch_active_load)
    assert callable(render_driver_app)


def test_lawson_profile_imports():
    from lp_helpers.lawson_profile import (
        CARRIER_NAME,
        LAWSON_SEED_LEADS,
        LAWSON_SIM_ROUTE,
        OWNERS,
        PLATFORM_TITLE,
    )

    assert "L & P" in CARRIER_NAME or "Freight" in CARRIER_NAME
    assert "BIG E" not in PLATFORM_TITLE
    assert len(OWNERS) >= 2
    assert len(LAWSON_SEED_LEADS) >= 4
    assert len(LAWSON_SIM_ROUTE) >= 2
    assert "Freight" in PLATFORM_TITLE or "L & P" in PLATFORM_TITLE


def test_fleet_context_default_tenant():
    from lp_helpers.fleet_context import get_tenant_context, list_known_tenants

    ctx = get_tenant_context()
    assert ctx.tenant_id == "lp-freight"
    assert "BIG E" not in ctx.platform_title
    assert len(ctx.operators) >= 2
    assert len(list_known_tenants()) >= 1


def test_multi_tenant_schema_and_repos(tmp_path, monkeypatch):
    monkeypatch.setenv("LP_DATA_DIR", str(tmp_path))
    from lp_helpers import database as dbmod
    from lp_helpers.repositories import leads as leads_repo
    from lp_helpers.repositories import loads as loads_repo
    from lp_helpers.tenancy import DEFAULT_TENANT_ID

    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "tenant_test.db")
    monkeypatch.setattr(dbmod, "ATTACHMENTS_DIR", tmp_path / "attachments")
    dbmod.init_db()

    with closing(dbmod.get_conn()) as conn:
        row = conn.execute(
            "SELECT id, name FROM tenants WHERE id=?", (DEFAULT_TENANT_ID,)
        ).fetchone()
        assert row is not None
        assert row["name"]

        # tenant_id column exists on loads
        cols = {r[1] for r in conn.execute("PRAGMA table_info(loads)").fetchall()}
        assert "tenant_id" in cols

        lid = loads_repo.insert_load(
            conn,
            {
                "bol_number": "LP-T-001",
                "shipper": "Sibelco",
                "commodity": "Feldspar",
                "weight_tons": 24,
                "status": "Booked",
                "origin": "Spruce Pine, NC",
                "destination": "Central Georgia",
            },
            tenant_id=DEFAULT_TENANT_ID,
        )
        conn.commit()
        assert lid > 0
        df = loads_repo.list_loads(conn, tenant_id=DEFAULT_TENANT_ID)
        assert not df.empty
        assert (df["bol_number"] == "LP-T-001").any()
        # stored with tenant
        tid = conn.execute(
            "SELECT tenant_id FROM loads WHERE bol_number=?", ("LP-T-001",)
        ).fetchone()[0]
        assert tid == DEFAULT_TENANT_ID

        lead_id = leads_repo.insert_lead(
            conn,
            {"company": "Test Shipper", "status": "Hot", "priority": 1},
            tenant_id=DEFAULT_TENANT_ID,
        )
        conn.commit()
        assert lead_id > 0


def test_authz_and_telematics_port():
    from lp_helpers.ai.ports import RulesRateOptimizer
    from lp_helpers.authz import Principal, ROLE_DRIVER, can, default_principal, require
    from lp_helpers.integrations.telematics_port import (
        ManualTelematicsAdapter,
        get_telematics_port,
    )

    p = default_principal("lp-freight", "Phillip")
    assert can(p, "load.create")
    require(p, "lead.manage")

    d = Principal(user_id="1", tenant_id="lp-freight", role=ROLE_DRIVER, display_name="D")
    assert not can(d, "load.create")
    assert can(d, "load.status_own")

    port = ManualTelematicsAdapter()
    assert port.connection_status().ok
    fix = port.get_live_fix()
    assert fix is not None and fix.latitude
    assert get_telematics_port().connection_status().provider in ("manual", "traccar")

    sug = RulesRateOptimizer().suggest(
        commodity="Feldspar", weight_tons=24, loaded_miles=285, deadhead_miles=50
    )
    assert sug.rate_per_ton > 0 and sug.total_revenue > 0


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


def test_traccar_fetch_fleet_structure():
    from lp_helpers.traccar_live import TraccarLive

    client = TraccarLive(get_secret=lambda _s, _k, d="": d, url="http://localhost:8082")
    client._device_names = {1: "Lawson Truck 1"}
    client.fetch_devices = lambda: [{"id": 1, "name": "Lawson Truck 1", "status": "online"}]  # type: ignore[method-assign]
    client.fetch_positions = lambda device_id=None: [  # type: ignore[method-assign]
        {
            "deviceId": 1,
            "latitude": 35.9,
            "longitude": -82.1,
            "speed": 50.0,
            "fixTime": "2026-07-08T12:00:00Z",
        }
    ]
    fleet = client.fetch_fleet()
    assert len(fleet) == 1
    assert fleet[0]["device_name"] == "Lawson Truck 1"
    assert fleet[0]["latitude"] == 35.9


def test_traccar_live_offline_graceful():
    from lp_helpers.traccar_live import TraccarLive

    client = TraccarLive(
        get_secret=lambda s, k, d="": d,
        url="http://127.0.0.1:1",
        api_token="",
    )
    status = client.connection_status()
    assert "ok" in status
    assert status["ok"] is False
    assert client.fetch_fleet() == []


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


def test_emergency_message_format():
    from lp_helpers.emergency_alerts import build_emergency_context, format_emergency_message

    ctx = build_emergency_context(
        "medical",
        driver="Phillip",
        truck_label="L&P Lawson End-Dump",
        load={"bol_number": "LP-1", "commodity": "Feldspar", "weight_tons": 24},
        gps_fix={"latitude": 35.9, "longitude": -82.1, "speed_mph": 0},
    )
    msg = format_emergency_message(ctx)
    assert "MEDICAL" in msg
    assert "Phillip" in msg
    assert "35.90000" in msg
    assert "911" in msg


def test_emergency_sms_blocklist():
    from lp_helpers.emergency_alerts import (
        OFFICIAL_EMERGENCY_DIAL,
        is_sms_blocked_number,
    )

    assert is_sms_blocked_number("911")
    assert is_sms_blocked_number("+1911")
    assert is_sms_blocked_number("988")
    assert is_sms_blocked_number("511")
    assert is_sms_blocked_number("18008325660")
    assert not is_sms_blocked_number("+18285551234")
    dial_ids = {d["id"] for d in OFFICIAL_EMERGENCY_DIAL}
    assert "911" in dial_ids
    assert "fmcsa" in dial_ids
    assert "poison" in dial_ids
    assert "phillip_phone" not in dial_ids
    assert "lawson_phone" not in dial_ids


def test_mobile_web_urls(monkeypatch):
    from lp_helpers.mobile_web import app_start_url, driver_start_url

    monkeypatch.delenv("LP_WEB_MODE", raising=False)
    monkeypatch.setenv("LP_APP_URL", "http://127.0.0.1:8502")
    assert app_start_url() == "http://127.0.0.1:8502/"
    assert driver_start_url() == "http://127.0.0.1:8502/?view=driver"

    monkeypatch.setenv("LP_WEB_MODE", "1")
    monkeypatch.setenv("LP_APP_URL", "https://dispatch.lpfreight.com")
    assert app_start_url() == "https://dispatch.lpfreight.com/app/"
    assert driver_start_url() == "https://dispatch.lpfreight.com/app/?view=driver"


def test_new_load_logged_sms_template():
    import app as platform

    msg = platform.format_sms(
        "new_load_logged",
        {
            "shipper": "Sibelco",
            "commodity": "Feldspar",
            "weight_tons": 24.0,
            "bol_number": "LP-TEST-002",
            "status": "Potential",
            "origin": "Spruce Pine, NC",
            "destination": "Central Georgia (Kohler area)",
            "driver": "Phillip",
        },
    )
    assert "NEW LOAD" in msg
    assert "Sibelco" in msg
    assert "LP-TEST-002" in msg


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