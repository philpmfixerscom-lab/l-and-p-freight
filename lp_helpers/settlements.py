"""Owner-operator settlements lite — close a delivered load to a pay statement.

total_pay maps to net after empty-mile cost (O/O view: what the trip netted
after deadhead fuel+ops). Notes carry the full revenue / deadhead breakdown.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Default cost rates (match app.py constants; callers should pass explicit values)
DEFAULT_FUEL_PER_MI = 0.72
DEFAULT_OPS_PER_MI = 0.18


class SettlementExistsError(ValueError):
    """Raised when a Closed settlement already exists for the load."""

    def __init__(self, load_id: Any, existing_id: int):
        self.load_id = load_id
        self.existing_id = existing_id
        super().__init__(
            f"Settlement already closed for load_id={load_id} (id={existing_id})"
        )


def compute_settlement_for_load(
    load: dict[str, Any],
    *,
    fuel_per_mi: float = DEFAULT_FUEL_PER_MI,
    ops_per_mi: float = DEFAULT_OPS_PER_MI,
    driver_name: str = "Owner-Operator",
) -> dict[str, Any]:
    """Compute O/O settlement numbers for a load.

    revenue = total_revenue or rate_per_ton * weight_tons
    deadhead_cost = deadhead_miles * (fuel_per_mi + ops_per_mi)
    net = revenue - deadhead_cost
    total_pay = net  (documented: "net after empty miles")
    """
    try:
        revenue = float(load.get("total_revenue") or 0)
    except (TypeError, ValueError):
        revenue = 0.0
    if revenue <= 0:
        try:
            rate = float(load.get("rate_per_ton") or 0)
            weight = float(load.get("weight_tons") or 0)
            revenue = rate * weight
        except (TypeError, ValueError):
            revenue = 0.0

    try:
        deadhead_miles = float(load.get("deadhead_miles") or 0)
    except (TypeError, ValueError):
        deadhead_miles = 0.0
    try:
        loaded_miles = float(
            load.get("loaded_miles") or load.get("miles") or 0
        )
    except (TypeError, ValueError):
        loaded_miles = 0.0

    cost_per_mi = float(fuel_per_mi) + float(ops_per_mi)
    deadhead_cost = round(deadhead_miles * cost_per_mi, 2)
    revenue = round(revenue, 2)
    net = round(revenue - deadhead_cost, 2)

    notes = (
        f"net after empty miles | revenue=${revenue:.2f} "
        f"deadhead={deadhead_miles:.1f}mi @ ${cost_per_mi:.2f}/mi "
        f"(fuel ${fuel_per_mi:.2f}+ops ${ops_per_mi:.2f}) = ${deadhead_cost:.2f} | "
        f"net=${net:.2f}"
    )

    return {
        "load_id": load.get("id"),
        "driver_name": driver_name,
        "planned_loaded_miles": loaded_miles,
        "actual_loaded_miles": loaded_miles,
        "planned_empty_miles": deadhead_miles,
        "actual_empty_miles": deadhead_miles,
        "loaded_rate": float(load.get("rate_per_ton") or 0),
        "empty_rate": cost_per_mi,
        "bonuses": 0.0,
        "deductions": deadhead_cost,
        "accessorials": 0.0,
        "total_pay": net,
        "variance_pct": 0.0,
        "status": "Closed",
        "notes": notes,
        "revenue": revenue,
        "deadhead_cost": deadhead_cost,
        "net": net,
        "fuel_per_mi": float(fuel_per_mi),
        "ops_per_mi": float(ops_per_mi),
        "cost_per_mi": cost_per_mi,
    }


def existing_closed_settlement_id(conn: Any, load_id: Any) -> int | None:
    """Return id of an existing Closed settlement for load_id, or None."""
    if load_id is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT id FROM settlements
            WHERE load_id = ? AND LOWER(COALESCE(status, '')) = 'closed'
            ORDER BY id DESC LIMIT 1
            """,
            (load_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"] if hasattr(row, "keys") else row[0])
    except Exception:
        return None


def insert_settlement(conn: Any, settlement: dict[str, Any]) -> int:
    """Insert into settlements table. Raises SettlementExistsError if already Closed.

    Returns new row id.
    """
    load_id = settlement.get("load_id")
    existing = existing_closed_settlement_id(conn, load_id)
    if existing is not None:
        raise SettlementExistsError(load_id, existing)

    cur = conn.execute(
        """
        INSERT INTO settlements (
            load_id, asset_id, driver_name,
            planned_loaded_miles, actual_loaded_miles,
            planned_empty_miles, actual_empty_miles,
            loaded_rate, empty_rate,
            bonuses, deductions, accessorials,
            total_pay, variance_pct, status, notes, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
        """,
        (
            load_id,
            settlement.get("asset_id"),
            settlement.get("driver_name"),
            float(settlement.get("planned_loaded_miles") or 0),
            float(settlement.get("actual_loaded_miles") or 0),
            float(settlement.get("planned_empty_miles") or 0),
            float(settlement.get("actual_empty_miles") or 0),
            float(settlement.get("loaded_rate") or 0),
            float(settlement.get("empty_rate") or 0),
            float(settlement.get("bonuses") or 0),
            float(settlement.get("deductions") or 0),
            float(settlement.get("accessorials") or 0),
            float(settlement.get("total_pay") or 0),
            settlement.get("variance_pct"),
            settlement.get("status") or "Closed",
            settlement.get("notes") or "",
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def fetch_recent_settlements(conn: Any, limit: int = 10) -> list[dict[str, Any]]:
    """Recent settlements joined to load shipper/bol when available."""
    try:
        rows = conn.execute(
            """
            SELECT s.*, l.bol_number, l.shipper, l.commodity, l.status AS load_status
            FROM settlements s
            LEFT JOIN loads l ON l.id = s.load_id
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        try:
            rows = conn.execute(
                "SELECT * FROM settlements ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


def _latin1_safe(text: str) -> str:
    """Coerce text to Helvetica-safe latin-1 (replace unsupported chars)."""
    return str(text or "").encode("latin-1", errors="replace").decode("latin-1")


def generate_settlement_pdf(
    settlement: dict[str, Any],
    load: dict[str, Any] | None = None,
) -> bytes:
    """Simple settlement statement PDF via fpdf2 (offline)."""
    load = load or {}
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError as exc:
        raise ImportError("Install fpdf2: pip install fpdf2") from exc

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(
        0,
        10,
        _latin1_safe("L & P Freight - Settlement Statement"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        _latin1_safe("Owner-operator closeout - net after empty miles"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    created = settlement.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = [
        ("Settlement #", str(settlement.get("id") or "DRAFT")),
        ("Date", str(created)[:19]),
        ("Driver", str(settlement.get("driver_name") or "-")),
        ("Status", str(settlement.get("status") or "Closed")),
        ("BOL", str(load.get("bol_number") or "-")),
        ("Shipper", str(load.get("shipper") or "-")),
        ("Commodity", str(load.get("commodity") or "-")),
        ("Lane", f"{load.get('origin') or '-'} -> {load.get('destination') or '-'}"),
        ("Loaded miles", f"{float(settlement.get('actual_loaded_miles') or 0):.1f}"),
        ("Empty miles", f"{float(settlement.get('actual_empty_miles') or 0):.1f}"),
        (
            "Revenue",
            f"${float(settlement.get('revenue') or load.get('total_revenue') or 0):,.2f}",
        ),
        (
            "Deadhead cost",
            f"${float(settlement.get('deadhead_cost') or settlement.get('deductions') or 0):,.2f}",
        ),
        ("Total pay (net)", f"${float(settlement.get('total_pay') or 0):,.2f}"),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 7, _latin1_safe(label), border=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(
            0,
            7,
            _latin1_safe(str(value)[:80]),
            border=1,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    notes = settlement.get("notes")
    if notes:
        pdf.ln(4)
        pdf.multi_cell(0, 6, _latin1_safe(f"Notes: {notes}"))

    pdf.ln(8)
    pdf.cell(
        0,
        7,
        _latin1_safe(f"Statement date: {date.today().isoformat()}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        7,
        _latin1_safe("Driver sign-off: _________________________  Date: __________"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
