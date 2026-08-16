"""Tests for due-follow-up queries, logging, and opportunity status."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

import lp_helpers.database as dbmod
from lp_helpers.load_board import (
    OPPORTUNITY_STATUSES,
    insert_opportunity,
    update_opportunity_status,
)
from lp_helpers.pipeline import fetch_due_followups, log_lead_followup


def _init(tmp_path: Path):
    db = tmp_path / "test_pipeline.db"
    old = dbmod.DB_PATH
    dbmod.DB_PATH = db
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            contact_name TEXT,
            phone TEXT,
            status TEXT,
            priority INTEGER DEFAULT 5,
            last_contact TEXT,
            next_followup_date TEXT,
            followup_type TEXT,
            notes TEXT,
            commodity_focus TEXT
        );
        CREATE TABLE call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER,
            call_type TEXT,
            notes TEXT,
            outcome TEXT,
            logged_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE sms_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER,
            alert_type TEXT,
            message TEXT,
            sent_via TEXT DEFAULT 'clipboard',
            twilio_sid TEXT,
            logged_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT DEFAULT 'manual',
            lane TEXT NOT NULL,
            commodity TEXT,
            rate TEXT,
            contact TEXT,
            notes TEXT,
            status TEXT DEFAULT 'Open',
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    today = date.today()
    conn.execute(
        "INSERT INTO leads (id, company, status, priority, next_followup_date, followup_type) "
        "VALUES (1,'Sibelco','Hot',1,?,'Phone Call')",
        ((today - timedelta(days=3)).isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, priority, next_followup_date, followup_type) "
        "VALUES (2,'Covia','Active',2,?,'Text')",
        (today.isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, priority, next_followup_date) "
        "VALUES (3,'K-T Feldspar','Hot',3,?)",
        ((today + timedelta(days=5)).isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (4,'Ghost Co','Hot','')"
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (5,'Closed Co','Closed',?)",
        ((today - timedelta(days=1)).isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (6,'New Co','New',?)",
        ((today - timedelta(days=1)).isoformat(),),
    )
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


class TestFetchDueFollowups:
    def test_includes_overdue_and_today(self, db):
        due = fetch_due_followups()
        companies = {d["company"] for d in due}
        assert companies == {"Sibelco", "Covia", "New Co"}

    def test_excludes_future_and_blank(self, db):
        due = fetch_due_followups()
        companies = {d["company"] for d in due}
        assert "K-T Feldspar" not in companies
        assert "Ghost Co" not in companies

    def test_excludes_closed(self, db):
        due = fetch_due_followups()
        assert all(d["company"] != "Closed Co" for d in due)

    def test_hot_and_active_are_visible(self, db):
        """Dashboard used to hide these by filtering New/Contacted/Quote Sent."""
        due = fetch_due_followups()
        statuses = {d["company"]: d["status"] for d in due}
        assert statuses["Sibelco"] == "Hot"
        assert statuses["Covia"] == "Active"

    def test_overdue_label(self, db):
        due = {d["company"]: d for d in fetch_due_followups()}
        assert due["Sibelco"]["days_overdue"] == 3
        assert due["Sibelco"]["due_label"] == "3 days overdue"
        assert due["Covia"]["days_overdue"] == 0
        assert due["Covia"]["due_label"] == "due today"

    def test_as_of_override(self, db):
        past = date.today() - timedelta(days=10)
        assert fetch_due_followups(as_of=past) == []

    def test_accepts_datetime_text(self, db):
        conn = dbmod.get_conn()
        conn.execute(
            "UPDATE leads SET next_followup_date = ? WHERE id = 3",
            (f"{date.today().isoformat()} 08:30:00",),
        )
        conn.commit()
        conn.close()
        companies = {d["company"] for d in fetch_due_followups()}
        assert "K-T Feldspar" in companies


class TestLogLeadFollowup:
    def test_updates_contact_and_next_date(self, db):
        nxt = date.today() + timedelta(days=4)
        result = log_lead_followup(
            1,
            next_followup_date=nxt,
            followup_type="Email",
            note="Left a voicemail",
        )
        conn = dbmod.get_conn()
        lead = conn.execute("SELECT * FROM leads WHERE id=1").fetchone()
        conn.close()
        assert lead["last_contact"] == result["last_contact"]
        assert lead["next_followup_date"] == nxt.isoformat()
        assert lead["followup_type"] == "Email"
        assert "Left a voicemail" in (lead["notes"] or "")

    def test_writes_call_log(self, db):
        log_lead_followup(2, next_followup_date=date.today() + timedelta(days=2), note="Quoted $48/ton")
        conn = dbmod.get_conn()
        row = conn.execute("SELECT * FROM call_logs WHERE lead_id=2").fetchone()
        conn.close()
        assert row is not None
        assert row["notes"] == "Quoted $48/ton"
        assert row["outcome"] == "Followed up"

    def test_optional_sms_log_is_clipboard_only(self, db):
        result = log_lead_followup(
            2,
            next_followup_date=date.today() + timedelta(days=1),
            message="Hi, checking on feldspar this week.",
            channel="sms",
        )
        conn = dbmod.get_conn()
        sms = conn.execute("SELECT * FROM sms_log WHERE id=?", (result["sms_log_id"],)).fetchone()
        conn.close()
        assert sms["sent_via"] == "clipboard"
        assert sms["twilio_sid"] is None
        assert "feldspar" in sms["message"]

    def test_clears_due_list_when_rescheduled(self, db):
        log_lead_followup(1, next_followup_date=date.today() + timedelta(days=7))
        companies = {d["company"] for d in fetch_due_followups()}
        assert "Sibelco" not in companies

    def test_missing_lead_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            log_lead_followup(999, next_followup_date=date.today())


class TestOpportunityStatus:
    def test_default_open_then_advance(self, db):
        conn = dbmod.get_conn()
        oid = insert_opportunity(
            conn,
            lane="Spruce Pine, NC → Central GA",
            commodity="Feldspar",
            rate="$48/ton",
            contact="Dispatch",
        )
        conn.commit()
        row = conn.execute("SELECT status FROM opportunities WHERE id=?", (oid,)).fetchone()
        assert row["status"] == "Open"
        update_opportunity_status(oid, "Working", conn=conn)
        conn.commit()
        row = conn.execute("SELECT status FROM opportunities WHERE id=?", (oid,)).fetchone()
        conn.close()
        assert row["status"] == "Working"

    def test_won_and_lost(self, db):
        conn = dbmod.get_conn()
        oid = insert_opportunity(conn, lane="NC → GA", commodity="Mica", rate="$50", contact="")
        conn.commit()
        update_opportunity_status(oid, "Won", conn=conn)
        conn.commit()
        assert conn.execute("SELECT status FROM opportunities WHERE id=?", (oid,)).fetchone()["status"] == "Won"
        update_opportunity_status(oid, "Lost", conn=conn)
        conn.commit()
        conn.close()
        conn = dbmod.get_conn()
        assert conn.execute("SELECT status FROM opportunities WHERE id=?", (oid,)).fetchone()["status"] == "Lost"
        conn.close()

    def test_rejects_unknown_status(self, db):
        conn = dbmod.get_conn()
        oid = insert_opportunity(conn, lane="NC → GA", commodity="Clay", rate="", contact="")
        conn.commit()
        conn.close()
        with pytest.raises(ValueError, match="Unknown opportunity status"):
            update_opportunity_status(oid, "Quoted")

    def test_rejects_missing_id(self, db):
        with pytest.raises(ValueError, match="not found"):
            update_opportunity_status(404, "Open")

    def test_status_vocabulary(self, db):
        assert OPPORTUNITY_STATUSES == ("Open", "Working", "Won", "Lost")
