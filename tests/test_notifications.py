"""Tests for the notifications engine (derive, group, dismiss)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.notifications import (
    derive_notifications,
    get_notifications,
    dismiss_notification,
    group_notifications,
    CATEGORY_META,
)


def _init(tmp_path: Path):
    db = tmp_path / "test_notif.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT, status TEXT, created_at TEXT
        );
        CREATE TABLE loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bol_number TEXT, shipper TEXT, pickup_date TEXT, status TEXT,
            loaded_miles REAL, deadhead_miles REAL, destination TEXT, accepted_at TEXT
        );
        CREATE TABLE routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            load_id INTEGER, planned_loaded_miles REAL, planned_empty_miles REAL,
            google_miles REAL, actual_loaded_miles REAL, actual_empty_miles REAL,
            updated_at TEXT
        );
        CREATE TABLE notification_dismissals (key TEXT PRIMARY KEY, dismissed_at TEXT);
        """
    )
    conn.execute("INSERT INTO leads (id, company, status, created_at) VALUES (1,'Sibelco','Hot',datetime('now'))")
    conn.execute("INSERT INTO leads (id, company, status, created_at) VALUES (2,'Old Co','Hot','2020-01-01 00:00:00')")
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, pickup_date, status, loaded_miles, deadhead_miles, destination, accepted_at) "
        "VALUES (1,'LP-A','Sibelco','2020-01-01','In Transit',300,60,'GA',datetime('now'))"
    )
    conn.execute(
        "INSERT INTO loads (id, bol_number, shipper, pickup_date, status, loaded_miles, deadhead_miles, destination, accepted_at) "
        "VALUES (2,'LP-B','Covia','2020-01-01','Accepted',200,200,'GA',datetime('now'))"
    )
    conn.execute(
        "INSERT INTO routes (id, load_id, planned_loaded_miles, planned_empty_miles, google_miles, actual_loaded_miles, actual_empty_miles, updated_at) "
        "VALUES (1, 1, 280, 285, 565, 420, 285, datetime('now'))"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS notification_dismissals (key TEXT PRIMARY KEY, dismissed_at TEXT)")
    conn.commit()
    conn.close()
    return old


@pytest.fixture()
def db(tmp_path: Path):
    old = _init(tmp_path)
    try:
        yield
    finally:
        dbmod.DB_PATH = old


class TestDeriveNotifications:
    def test_categories_present(self, db):
        cats = {n["category"] for n in derive_notifications(dbmod.get_conn())}
        assert "lead" in cats          # Sibelco (recent)
        assert "late" in cats          # LP-A pickup in past
        assert "deadhead" in cats      # LP-B 50% empty
        assert "accepted" in cats      # both accepted
        assert "variance" in cats      # route flagged

    def test_old_lead_excluded(self, db):
        titles = [n["title"] for n in derive_notifications(dbmod.get_conn())]
        assert not any("Old Co" in t for t in titles)

    def test_keys_unique(self, db):
        keys = [n["key"] for n in derive_notifications(dbmod.get_conn())]
        assert len(keys) == len(set(keys))


class TestGroupAndDismiss:
    def test_unread_count(self, db):
        data = get_notifications()
        assert data["unread"] > 0

    def test_dismiss_removes(self, db):
        before = get_notifications()["unread"]
        dismiss_notification("lead:1")
        after = get_notifications()["unread"]
        assert after == before - 1
        # stays dismissed
        assert after == get_notifications()["unread"]

    def test_grouping(self, db):
        items = derive_notifications(dbmod.get_conn())
        grouped = group_notifications(items)
        assert sum(len(v) for v in grouped.values()) == len(items)


def test_category_meta_complete():
    for cat in ("lead", "accepted", "late", "deadhead", "variance", "eld"):
        assert cat in CATEGORY_META
