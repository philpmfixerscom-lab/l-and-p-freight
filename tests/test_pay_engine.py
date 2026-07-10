"""Tests for the driver pay engine — Lawson's 'pay for miles actually driven' rule."""

from __future__ import annotations

import pytest

from lp_helpers.pay_engine import driver_pay, mileage_reconciliation, pay_decision


class TestDriverPayAlwaysActual:
    def test_basic_actual_pay(self):
        pay = driver_pay(280, 285, 1.75, 0.85)
        assert pay.loaded_pay == pytest.approx(490.0)
        assert pay.empty_pay == pytest.approx(242.25)
        assert pay.total_pay == pytest.approx(732.25)

    def test_bonuses_accessorials_deductions(self):
        pay = driver_pay(300, 0, 1.80, 0.90, bonuses=100.0, accessorials=50.0, deductions=25.0)
        assert pay.base_pay == pytest.approx(540.0)
        assert pay.total_pay == pytest.approx(665.0)

    def test_negative_miles_clamped(self):
        pay = driver_pay(-50, -10, 1.75, 0.85)
        assert pay.total_pay == 0.0

    def test_google_short_still_pays_actual(self):
        # Google shows 280 loaded miles but driver actually drove 310.
        # Driver must be paid for 310, not 280.
        pay = driver_pay(310, 285, 1.75, 0.85)
        google_based = driver_pay(280, 285, 1.75, 0.85)
        assert pay.total_pay > google_based.total_pay
        assert pay.loaded_pay == pytest.approx(310 * 1.75)


class TestMileageReconciliation:
    def test_google_short_flags_extra_miles(self):
        r = mileage_reconciliation(310, 0, google_miles=280)
        assert r["pay_miles"] == 310          # always actual
        assert r["basis_miles"] == 280
        assert r["extra_miles"] == 30
        assert r["basis_source"] == "google"

    def test_within_tolerance_not_flagged_but_pays_actual(self):
        r = mileage_reconciliation(290, 285, google_miles=565)
        assert r["pay_miles"] == 575          # actual, even though within tolerance
        assert r["flagged"] is False

    def test_outside_tolerance_flagged(self):
        r = mileage_reconciliation(420, 285, google_miles=565)
        assert r["flagged"] is True

    def test_alternate_route_same_miles_same_basis(self):
        # Different route, same total miles => zero variance.
        r = mileage_reconciliation(285, 280, planned_loaded_miles=285, planned_empty_miles=280)
        assert r["extra_miles"] == 0
        assert r["variance_pct"] == 0.0

    def test_planned_basis_when_no_google(self):
        r = mileage_reconciliation(300, 275, planned_loaded_miles=280, planned_empty_miles=285)
        assert r["basis_source"] == "planned"
        assert r["basis_miles"] == 565

    def test_no_basis(self):
        r = mileage_reconciliation(300, 0)
        assert r["basis_source"] == "none"
        assert r["pay_miles"] == 300


class TestPayDecision:
    def test_short_google_adds_dollars(self):
        d = pay_decision(310, 0, 1.75, 0.0, google_miles=280)
        assert d["extra_miles"] == 30
        assert d["dollar_impact_vs_basis"] > 0
        assert "policy" in d["message"].lower()

    def test_total_pay_is_actual(self):
        d = pay_decision(310, 285, 1.75, 0.85, google_miles=280)
        assert d["total_pay"] == pytest.approx(driver_pay(310, 285, 1.75, 0.85).total_pay)

    def test_flag_surfaces_in_message(self):
        d = pay_decision(450, 285, 1.75, 0.85, google_miles=565, tolerance_pct=10.0)
        assert d["flagged"] is True
        assert "review" in d["message"].lower()
