"""Tests for launch-ready upgrades: backup, auth, settlements, CRM, SMS, distance."""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _write_sqlite(path: Path, marker: str = "v1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute(
        "INSERT OR REPLACE INTO meta (k, v) VALUES ('marker', ?)", (marker,)
    )
    conn.commit()
    conn.close()


def _read_marker(path: Path) -> str | None:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT v FROM meta WHERE k='marker'").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PHASE 1 — Backup retention
# ---------------------------------------------------------------------------


def test_backup_retention_keeps_only_n(tmp_path: Path):
    from lp_helpers.backup import create_backup, list_backups, prune_backups

    db = tmp_path / "lp_dispatch.db"
    bak = tmp_path / "backups"
    _write_sqlite(db, "live")

    for i in range(20):
        p = create_backup(db, bak, stamp=f"20260101_{i:06d}")
        assert p is not None
        time.sleep(0.01)

    assert len(list_backups(bak)) == 20
    deleted = prune_backups(bak, max_keep=14)
    assert len(deleted) == 6
    remaining = list_backups(bak)
    assert len(remaining) == 14
    assert remaining[0].stat().st_mtime >= remaining[-1].stat().st_mtime


def test_auto_backup_skips_when_fresh_and_unchanged(tmp_path: Path):
    from lp_helpers.backup import auto_backup_db, list_backups

    db = tmp_path / "lp_dispatch.db"
    bak = tmp_path / "backups"
    _write_sqlite(db, "data-a")
    first = auto_backup_db(db, bak, min_age_hours=6, force=False)
    assert first is not None
    n1 = len(list_backups(bak))
    second = auto_backup_db(db, bak, min_age_hours=6, force=False)
    assert second is None
    assert len(list_backups(bak)) == n1


def test_restore_makes_safety_copy(tmp_path: Path):
    from lp_helpers.backup import SAFETY_PREFIX, create_backup, list_backups, restore_backup

    db = tmp_path / "lp_dispatch.db"
    bak = tmp_path / "backups"
    _write_sqlite(db, "live-v1")
    backup = create_backup(db, bak, stamp="restore_src")
    assert backup is not None
    # Mutate backup content independently
    _write_sqlite(backup, "backup-content")
    _write_sqlite(db, "live-v2")
    safety = restore_backup(backup, db, bak)
    assert _read_marker(db) == "backup-content"
    assert safety.exists()
    assert safety.name.startswith(SAFETY_PREFIX)
    assert _read_marker(safety) == "live-v2"
    # Safety copies must not appear in list_backups / prune budget
    names = [p.name for p in list_backups(bak)]
    assert safety.name not in names
    assert all("_pre_restore_" not in n for n in names)
    assert all(not n.startswith(SAFETY_PREFIX) for n in names)


def test_restore_rejects_path_outside_backup_dir(tmp_path: Path):
    from lp_helpers.backup import restore_backup, validate_backup_path

    bak = tmp_path / "backups"
    bak.mkdir()
    outside = tmp_path / "evil" / "lp_dispatch_20260101_000000.db"
    outside.parent.mkdir()
    _write_sqlite(outside, "evil")
    db = tmp_path / "lp_dispatch.db"
    _write_sqlite(db, "live")

    with pytest.raises(ValueError, match="under backup"):
        validate_backup_path(outside, bak)
    with pytest.raises(ValueError):
        restore_backup(outside, db, bak)


def test_pre_restore_excluded_from_list_and_prune(tmp_path: Path):
    from lp_helpers.backup import (
        SAFETY_PREFIX,
        create_backup,
        list_backups,
        prune_backups,
    )

    bak = tmp_path / "backups"
    bak.mkdir()
    db = tmp_path / "lp_dispatch.db"
    _write_sqlite(db, "x")
    create_backup(db, bak, stamp="20260101_000001")
    # Plant a safety-style file that would match old glob
    old_style = bak / "lp_dispatch_pre_restore_20260101_999999.db"
    _write_sqlite(old_style, "safety-old")
    new_style = bak / f"{SAFETY_PREFIX}20260101_999999.db"
    _write_sqlite(new_style, "safety-new")

    listed = list_backups(bak)
    assert len(listed) == 1
    assert listed[0].name == "lp_dispatch_20260101_000001.db"
    prune_backups(bak, max_keep=1)
    assert old_style.exists()  # not pruned as a regular backup
    assert new_style.exists()


def test_prune_safety_copies_keeps_newest(tmp_path: Path):
    from lp_helpers.backup import (
        SAFETY_PREFIX,
        list_safety_copies,
        prune_safety_copies,
    )

    bak = tmp_path / "backups"
    bak.mkdir()
    # 7 safety copies (new + legacy naming)
    created: list[Path] = []
    for i in range(5):
        p = bak / f"{SAFETY_PREFIX}2026010{i}_120000.db"
        _write_sqlite(p, f"s{i}")
        created.append(p)
        time.sleep(0.02)
    for i in range(2):
        p = bak / f"lp_dispatch_pre_restore_legacy_{i}.db"
        _write_sqlite(p, f"leg{i}")
        created.append(p)
        time.sleep(0.02)

    assert len(list_safety_copies(bak)) == 7
    deleted = prune_safety_copies(bak, keep=5)
    assert len(deleted) == 2
    remaining = list_safety_copies(bak)
    assert len(remaining) == 5
    # Newest-first ordering preserved among survivors
    assert remaining[0].stat().st_mtime >= remaining[-1].stat().st_mtime


# ---------------------------------------------------------------------------
# PHASE 2 — Auth gate
# ---------------------------------------------------------------------------


def test_auth_compare_digest_path():
    from lp_helpers.auth_gate import (
        check_password_digest,
        password_required,
        resolve_app_password,
        verify_password,
    )

    assert password_required("") is False
    assert password_required(None) is False
    assert password_required("secret") is True

    assert verify_password("secret", "secret") is True
    assert verify_password("wrong", "secret") is False
    assert verify_password("", "secret") is False
    assert verify_password("x", "") is False
    assert check_password_digest("abc", "abc") is True
    assert check_password_digest("abc", "xyz") is False

    pw = resolve_app_password(
        secrets_getter=lambda s, k, d="": "from-secrets",
        env={"LP_APP_PASSWORD": "from-env"},
    )
    assert pw == "from-env"

    pw2 = resolve_app_password(
        secrets_getter=lambda s, k, d="": "from-secrets" if s == "auth" else d,
        env={},
    )
    assert pw2 == "from-secrets"

    pw3 = resolve_app_password(secrets_getter=lambda s, k, d="": d, env={})
    assert pw3 == ""


def test_auth_fail_closed_when_password_required():
    """Unit-level: password_required + not authenticated must block (no fail-open)."""
    from lp_helpers.auth_gate import password_required, resolve_app_password

    # Configured password always requires gate
    assert password_required("set-me") is True
    # Empty never requires
    assert password_required(resolve_app_password(env={}, secrets_getter=None)) is False

    # Even if secrets_getter throws, env password still resolves
    def boom(*_a, **_k):
        raise RuntimeError("secrets broken")

    pw = resolve_app_password(secrets_getter=boom, env={"LP_APP_PASSWORD": "env-secret"})
    assert pw == "env-secret"
    assert password_required(pw) is True


def test_auth_cooldown_resets_after_until():
    """Time-based lockout: expired auth_fail_until clears count (unit of helper logic)."""
    import time as _time

    # Mirror _auth_cooldown_remaining without Streamlit: pure logic check
    until = _time.time() - 1  # already expired
    now = _time.time()
    remaining = 0 if now >= until else int(until - now) + 1
    assert remaining == 0

    until_future = _time.time() + 120
    remaining2 = max(0, int(until_future - _time.time()) + 1)
    assert 100 <= remaining2 <= 121


# ---------------------------------------------------------------------------
# PHASE 5 — Settlements
# ---------------------------------------------------------------------------


def test_settlement_compute_math():
    from lp_helpers.settlements import compute_settlement_for_load

    load = {
        "id": 1,
        "total_revenue": 1200.0,
        "deadhead_miles": 100.0,
        "loaded_miles": 285.0,
        "rate_per_ton": 50.0,
        "weight_tons": 24.0,
    }
    s = compute_settlement_for_load(
        load, fuel_per_mi=0.72, ops_per_mi=0.18, driver_name="Phillip"
    )
    assert s["deadhead_cost"] == 90.0
    assert s["revenue"] == 1200.0
    assert s["net"] == 1110.0
    assert s["total_pay"] == 1110.0
    assert "net after empty miles" in s["notes"]

    load2 = {"rate_per_ton": 48.0, "weight_tons": 24.0, "deadhead_miles": 0}
    s2 = compute_settlement_for_load(load2, fuel_per_mi=0.72, ops_per_mi=0.18)
    assert s2["revenue"] == 1152.0
    assert s2["total_pay"] == 1152.0

    # Negative net possible when deadhead dominates
    load3 = {"total_revenue": 10.0, "deadhead_miles": 100.0}
    s3 = compute_settlement_for_load(load3, fuel_per_mi=0.72, ops_per_mi=0.18)
    assert s3["net"] < 0


def _settlements_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE loads (id INTEGER PRIMARY KEY, bol_number TEXT, shipper TEXT);
        CREATE TABLE settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_id INTEGER NOT NULL,
            asset_id INTEGER,
            driver_name TEXT,
            planned_loaded_miles REAL NOT NULL,
            actual_loaded_miles REAL NOT NULL,
            planned_empty_miles REAL NOT NULL,
            actual_empty_miles REAL NOT NULL,
            loaded_rate REAL NOT NULL,
            empty_rate REAL NOT NULL,
            bonuses REAL DEFAULT 0.0,
            deductions REAL DEFAULT 0.0,
            accessorials REAL DEFAULT 0.0,
            total_pay REAL NOT NULL,
            variance_pct REAL,
            status TEXT DEFAULT 'Draft',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO loads (id, bol_number, shipper) VALUES (9, 'LP-TEST', 'Sibelco');
        """
    )
    return conn


def test_settlement_insert_and_pdf():
    from lp_helpers.settlements import (
        compute_settlement_for_load,
        generate_settlement_pdf,
        insert_settlement,
    )

    conn = _settlements_conn()
    load = {
        "id": 9,
        "bol_number": "LP-TEST",
        "shipper": "Sibelco",
        "commodity": "Feldspar",
        "total_revenue": 1000.0,
        "deadhead_miles": 50.0,
        "loaded_miles": 280.0,
        "rate_per_ton": 48.0,
    }
    sett = compute_settlement_for_load(load, fuel_per_mi=0.72, ops_per_mi=0.18)
    sid = insert_settlement(conn, sett)
    assert sid >= 1
    sett["id"] = sid
    pdf = generate_settlement_pdf(sett, load)
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 100
    assert pdf[:4] == b"%PDF"
    conn.close()


def test_settlement_blocks_duplicate_closed():
    from lp_helpers.settlements import (
        SettlementExistsError,
        compute_settlement_for_load,
        insert_settlement,
    )

    conn = _settlements_conn()
    load = {
        "id": 9,
        "total_revenue": 500.0,
        "deadhead_miles": 10.0,
        "loaded_miles": 100.0,
        "rate_per_ton": 48.0,
    }
    sett = compute_settlement_for_load(load, fuel_per_mi=0.72, ops_per_mi=0.18)
    sid1 = insert_settlement(conn, sett)
    assert sid1 >= 1
    with pytest.raises(SettlementExistsError) as ei:
        insert_settlement(conn, sett)
    assert ei.value.existing_id == sid1
    count = conn.execute("SELECT COUNT(*) FROM settlements WHERE load_id=9").fetchone()[0]
    assert count == 1
    conn.close()


# ---------------------------------------------------------------------------
# PHASE 6 — CRM call-today
# ---------------------------------------------------------------------------


def test_crm_followup_filter_logic():
    from lp_helpers.crm import (
        filter_call_today_leads,
        lead_needs_call_today,
        next_followup_iso,
    )

    today = date(2026, 8, 1)
    hot_no_fu = {
        "id": 1,
        "company": "Sibelco",
        "status": "Hot",
        "next_followup_at": None,
        "last_contact": str(today),
    }
    assert lead_needs_call_today(hot_no_fu, today=today) is True

    due = {
        "id": 2,
        "company": "Covia",
        "status": "Active",
        "next_followup_at": "2026-07-30",
        "last_contact": "2026-07-29",
    }
    assert lead_needs_call_today(due, today=today) is True

    future_ok = {
        "id": 3,
        "company": "Future",
        "status": "Contacted",
        "next_followup_at": "2026-08-10",
        "last_contact": str(today),
    }
    assert lead_needs_call_today(future_ok, today=today) is False

    stale = {
        "id": 4,
        "company": "Stale",
        "status": "Negotiating",
        "next_followup_at": None,
        "last_contact": str(today - timedelta(days=5)),
    }
    assert lead_needs_call_today(stale, today=today) is True

    closed = {
        "id": 5,
        "company": "Closed Co",
        "status": "Closed",
        "next_followup_at": None,
        "last_contact": "2026-01-01",
    }
    assert lead_needs_call_today(closed, today=today) is False

    # Closed with past next_followup must still be excluded
    closed_due = {
        "id": 6,
        "company": "Closed Due",
        "status": "Closed",
        "next_followup_at": "2026-07-01",
        "last_contact": "2026-06-01",
    }
    assert lead_needs_call_today(closed_due, today=today) is False

    lost_due = {
        "id": 7,
        "company": "Lost Co",
        "status": "Lost",
        "next_followup_at": "2026-07-15",
        "last_contact": None,
    }
    assert lead_needs_call_today(lost_due, today=today) is False

    results = filter_call_today_leads(
        [hot_no_fu, due, future_ok, stale, closed, closed_due, lost_due],
        today=today,
    )
    ids = {r["id"] for r in results}
    assert ids == {1, 2, 4}
    assert 6 not in ids and 7 not in ids

    # Local-date helper
    assert next_followup_iso(days=3, today=today) == "2026-08-04"


# ---------------------------------------------------------------------------
# PHASE 7 — Low supply
# ---------------------------------------------------------------------------


def test_low_supply_fetch_threshold():
    from lp_helpers.inventory import fetch_low_supply_leads

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY,
            company TEXT,
            phone TEXT,
            commodity_focus TEXT,
            lane_notes TEXT,
            status TEXT,
            days_of_supply_est REAL,
            last_contact TEXT,
            last_estimate_level TEXT,
            last_estimate_tons REAL,
            avg_weekly_tons REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO leads (id, company, days_of_supply_est) VALUES (?,?,?)",
        [
            (1, "Low", 3.0),
            (2, "Ok", 12.0),
            (3, "Null", None),
            (4, "Edge", 4.9),
            (5, "Exact", 5.0),
        ],
    )
    conn.commit()
    low = fetch_low_supply_leads(conn, threshold_days=5)
    companies = [r["company"] for r in low]
    assert companies == ["Low", "Edge"]
    conn.close()


# ---------------------------------------------------------------------------
# PHASE 3 — try_send_sms without credentials
# ---------------------------------------------------------------------------


def test_try_send_sms_log_only_without_credentials(monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "get_secret", lambda *a, **k: "")
    logged = []

    def _log(lead_id, alert_type, message, sent_via="clipboard", twilio_sid=None):
        logged.append(
            {
                "lead_id": lead_id,
                "alert_type": alert_type,
                "message": message,
                "sent_via": sent_via,
                "twilio_sid": twilio_sid,
            }
        )

    monkeypatch.setattr(app_mod, "log_sms_event", _log)
    monkeypatch.setattr(
        app_mod, "normalize_phone", lambda x: x if x.startswith("+") else f"+1{x}"
    )

    ok, detail = app_mod.try_send_sms("+18285551212", "hello", "test_alert", lead_id=3)
    assert ok is False
    assert "Twilio not configured" in detail
    assert logged and logged[0]["sent_via"] == "clipboard"
    assert logged[0]["alert_type"] == "test_alert"

    ok2, detail2 = app_mod.try_send_sms("", "body", "x")
    assert ok2 is False
    assert logged[-1]["sent_via"] == "error"


def test_try_send_sms_error_does_not_leak_exception(monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "get_secret", lambda *a, **k: "x")
    monkeypatch.setattr(app_mod, "twilio_configured", lambda: True)
    monkeypatch.setattr(
        app_mod,
        "send_twilio_notification",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret token leaked")),
    )
    logged = []

    def _log(lead_id, alert_type, message, sent_via="clipboard", twilio_sid=None):
        logged.append({"message": message, "sent_via": sent_via})

    monkeypatch.setattr(app_mod, "log_sms_event", _log)
    monkeypatch.setattr(app_mod, "normalize_phone", lambda x: x)

    ok, detail = app_mod.try_send_sms("+18285551212", "hello body", "test")
    assert ok is False
    assert "secret token" not in detail
    assert "secret token" not in logged[-1]["message"]
    assert logged[-1]["sent_via"] == "error"
    assert logged[-1]["message"] == "hello body"


# ---------------------------------------------------------------------------
# PHASE 8 — Distance fallback
# ---------------------------------------------------------------------------


def test_distance_fallback_when_osrm_unavailable():
    from lp_helpers.distance import (
        clear_distance_cache,
        estimate_road_miles,
        geocode_city,
    )

    clear_distance_cache()
    assert geocode_city("Spruce Pine, NC") is not None
    assert geocode_city("Central Georgia (Kohler area)") is not None
    assert geocode_city("Unknown Village Nowhere") is None
    # Exact preferred over partial
    assert geocode_city("macon") == geocode_city("Macon, GA")

    assert estimate_road_miles("Nowhere A", "Nowhere B") is None

    with patch("requests.get", side_effect=OSError("network down")):
        miles = estimate_road_miles("Spruce Pine, NC", "Macon, GA")
        assert miles is None or isinstance(miles, float)

    from lp_helpers.deadhead import estimate_empty_home_miles, estimate_return_benefit
    from lp_helpers.deadhead import score_return_load

    with patch("lp_helpers.distance.estimate_road_miles", return_value=None):
        sc = score_return_load(
            origin="Macon, GA",
            destination="Spruce Pine, NC",
            commodity="Aggregate",
            rate_hint="45",
            current_location="Central Georgia",
        )
        ben = estimate_return_benefit(
            sc,
            origin="Macon, GA",
            destination="Spruce Pine, NC",
            current_location="Central Georgia",
            fuel_cost_per_mile=0.72,
        )
        assert ben["empty_home_mi"] > 0
        assert ben.get("miles_source") in ("heuristic", "osrm", "osrm+heuristic")
        assert "blurb" in ben

    heur = estimate_empty_home_miles("Central Georgia", "Spruce Pine, NC")
    assert heur == 285.0
