"""Tests for the Dashboard follow-up queue (crm-style predicate) and Leads save path."""

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
from lp_helpers.pipeline import (
    ACTIVE_PIPELINE_STATUSES,
    STALE_CONTACT_DAYS,
    fetch_due_followups,
    lead_needs_call_today,
    log_lead_followup,
)


TODAY = date(2026, 8, 16)


def _lead(**kwargs):
    base = {
        "company": "Test",
        "status": "Active",
        "last_contact": None,
        "next_followup_date": None,
    }
    base.update(kwargs)
    return base


class TestLeadNeedsCallToday:
    """Port of main crm.lead_needs_call_today onto next_followup_date / master statuses."""

    def test_dated_due_and_overdue(self):
        assert lead_needs_call_today(_lead(next_followup_date=TODAY.isoformat()), today=TODAY)
        assert lead_needs_call_today(
            _lead(next_followup_date=(TODAY - timedelta(days=2)).isoformat()),
            today=TODAY,
        )

    def test_future_date_with_fresh_contact_is_off(self):
        assert not lead_needs_call_today(
            _lead(
                status="Active",
                next_followup_date=(TODAY + timedelta(days=5)).isoformat(),
                last_contact=TODAY.isoformat(),
            ),
            today=TODAY,
        )

    def test_hot_with_null_followup(self):
        assert lead_needs_call_today(_lead(status="Hot"), today=TODAY)
        assert lead_needs_call_today(_lead(status="Hot", next_followup_date=""), today=TODAY)

    def test_hot_reads_next_followup_date_not_at(self):
        """Master column is next_followup_date; next_followup_at is accepted as alias only."""
        assert lead_needs_call_today(
            {"status": "Active", "last_contact": TODAY.isoformat(), "next_followup_date": TODAY.isoformat()},
            today=TODAY,
        )
        assert lead_needs_call_today(
            {"status": "Active", "last_contact": TODAY.isoformat(), "next_followup_at": TODAY.isoformat()},
            today=TODAY,
        )

    def test_stale_or_null_last_contact_on_pipeline(self):
        assert lead_needs_call_today(_lead(status="Quote Sent"), today=TODAY)
        assert lead_needs_call_today(
            _lead(
                status="Negotiating",
                last_contact=(TODAY - timedelta(days=STALE_CONTACT_DAYS)).isoformat(),
                next_followup_date=(TODAY + timedelta(days=4)).isoformat(),
            ),
            today=TODAY,
        )
        assert not lead_needs_call_today(
            _lead(
                status="Contacted",
                last_contact=(TODAY - timedelta(days=STALE_CONTACT_DAYS - 1)).isoformat(),
                next_followup_date=(TODAY + timedelta(days=4)).isoformat(),
            ),
            today=TODAY,
        )

    def test_terminal_never_queued_even_if_date_due(self):
        due = (TODAY - timedelta(days=1)).isoformat()
        for status in ("Booked", "Closed", "Not Interested", "On Hold"):
            assert not lead_needs_call_today(
                _lead(status=status, next_followup_date=due),
                today=TODAY,
            )

    def test_active_pipeline_vocab(self):
        assert ACTIVE_PIPELINE_STATUSES == {
            "Hot", "Active", "New", "Contacted", "Quote Sent", "Negotiating"
        }
        assert STALE_CONTACT_DAYS == 3


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
        "INSERT INTO leads (id, company, status, priority, last_contact, next_followup_date) "
        "VALUES (3,'K-T Feldspar','Hot',3,?,?)",
        (today.isoformat(), (today + timedelta(days=5)).isoformat()),
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
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (7,'Booked Co','Booked',?)",
        ((today - timedelta(days=2)).isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (8,'Negotiating Co','Negotiating',?)",
        (today.isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (9,'Passed Co','Not Interested',?)",
        ((today - timedelta(days=1)).isoformat(),),
    )
    conn.execute(
        "INSERT INTO leads (id, company, status, next_followup_date) "
        "VALUES (10,'Hold Co','On Hold',?)",
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
    def test_includes_dated_hot_stale_and_negotiating(self, db):
        companies = {d["company"] for d in fetch_due_followups()}
        assert {"Sibelco", "Covia", "Ghost Co", "New Co", "Negotiating Co"} <= companies

    def test_hot_blank_followup_is_queued(self, db):
        assert any(d["company"] == "Ghost Co" for d in fetch_due_followups())

    def test_future_hot_with_fresh_contact_is_off(self, db):
        companies = {d["company"] for d in fetch_due_followups()}
        assert "K-T Feldspar" not in companies

    def test_excludes_terminal(self, db):
        companies = {d["company"] for d in fetch_due_followups()}
        assert "Closed Co" not in companies
        assert "Booked Co" not in companies
        assert "Passed Co" not in companies
        assert "Hold Co" not in companies

    def test_hot_and_active_are_visible(self, db):
        statuses = {d["company"]: d["status"] for d in fetch_due_followups()}
        assert statuses["Sibelco"] == "Hot"
        assert statuses["Covia"] == "Active"

    def test_overdue_label(self, db):
        due = {d["company"]: d for d in fetch_due_followups()}
        assert due["Sibelco"]["days_overdue"] == 3
        assert due["Sibelco"]["due_label"] == "3 days overdue"
        assert due["Covia"]["days_overdue"] == 0
        assert due["Covia"]["due_label"] == "due today"
        assert due["Ghost Co"]["due_label"] == "hot — no follow-up set"

    def test_accepts_datetime_text(self, db):
        conn = dbmod.get_conn()
        conn.execute(
            "UPDATE leads SET last_contact = ?, next_followup_date = ? WHERE id = 3",
            (None, f"{date.today().isoformat()} 08:30:00"),
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

    def test_status_vocabulary(self, db):
        assert OPPORTUNITY_STATUSES == ("Open", "Working", "Won", "Lost")
