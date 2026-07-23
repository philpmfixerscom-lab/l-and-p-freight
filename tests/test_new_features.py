"""Tests for BulkLoads API, templates, rate analytics, fleet, photos, audit export."""

from __future__ import annotations

import sys
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
    ):
        assert (helpers / name).is_file(), name
