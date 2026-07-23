"""General-purpose audit trail + PDF export for contracts and audit log."""

from __future__ import annotations

import io
import zipfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from zipfile import ZIP_DEFLATED

import pandas as pd

from lp_helpers.database import ATTACHMENTS_DIR, get_conn

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    detail TEXT,
    actor TEXT DEFAULT 'system',
    meta_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
"""


def ensure_audit_table(conn) -> None:
    conn.executescript(AUDIT_SCHEMA)


def log_audit(
    action: str,
    *,
    entity_type: str = "",
    entity_id: str | int | None = None,
    detail: str = "",
    actor: str = "system",
    meta_json: str | None = None,
    conn=None,
) -> int:
    """Insert an audit row. Safe to call from UI and services."""
    owns = conn is None
    if owns:
        conn = get_conn()
    try:
        ensure_audit_table(conn)
        cur = conn.execute(
            """
            INSERT INTO audit_log (action, entity_type, entity_id, detail, actor, meta_json)
            VALUES (?,?,?,?,?,?)
            """,
            (
                action,
                entity_type or None,
                str(entity_id) if entity_id is not None else None,
                detail or None,
                actor or "system",
                meta_json,
            ),
        )
        if owns:
            conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        if owns:
            conn.close()


def fetch_audit_log(
    *,
    limit: int = 500,
    entity_type: str | None = None,
    action: str | None = None,
) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        ensure_audit_table(conn)
        clauses: list[str] = []
        params: list[Any] = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if action:
            clauses.append("action = ?")
            params.append(action)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return pd.read_sql_query(
            f"SELECT * FROM audit_log {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            conn,
            params=params,
        )


def generate_audit_log_pdf(
    audit_df: pd.DataFrame | None = None,
    *,
    title: str = "L & P Freight — Full Audit Log",
    limit: int = 500,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if audit_df is None:
        audit_df = fetch_audit_log(limit=limit)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(LETTER),
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title.replace("&", "&amp;"), styles["Heading1"]),
        Paragraph(
            f"Exported {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(audit_df)} events",
            styles["Normal"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if audit_df is None or audit_df.empty:
        story.append(Paragraph("No audit events recorded yet.", styles["Normal"]))
    else:
        cols = ["created_at", "action", "entity_type", "entity_id", "actor", "detail"]
        show = [c for c in cols if c in audit_df.columns]
        header = [c.replace("_", " ").title() for c in show]
        rows = [header]
        for _, r in audit_df.iterrows():
            rows.append(
                [
                    str(r.get(c, "") or "")[:80]
                    for c in show
                ]
            )
        col_w = [1.4 * inch, 1.3 * inch, 1.1 * inch, 0.9 * inch, 1.0 * inch, 3.6 * inch]
        col_w = col_w[: len(show)]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1628")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_contracts_bundle_pdf(
    loads_df: pd.DataFrame,
    *,
    bol_pdf_fn: Callable[[dict[str, Any]], bytes] | None = None,
    app_version: str = "4.4",
) -> bytes:
    """
    Single multi-page PDF summarizing all loads as contract-style records.
    (Full branded BOL per load is available via generate_all_contracts_zip.)
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("L &amp; P Freight — All Load Contracts", styles["Heading1"]),
        Paragraph(
            f"Contract summary export · {date.today()} · Platform v{app_version} · "
            f"{len(loads_df)} load(s)",
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
    ]

    if loads_df.empty:
        story.append(Paragraph("No loads available to export.", styles["Normal"]))
        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    # Index page
    idx_rows = [["#", "BOL", "Shipper", "Lane", "Revenue", "Status"]]
    for i, (_, r) in enumerate(loads_df.iterrows(), start=1):
        lane = f"{r.get('origin', '')} → {r.get('destination', '')}"
        idx_rows.append(
            [
                str(i),
                str(r.get("bol_number", "")),
                str(r.get("shipper", ""))[:28],
                lane[:36],
                f"${float(r.get('total_revenue') or 0):,.0f}",
                str(r.get("status", "")),
            ]
        )
    t = Table(
        idx_rows,
        colWidths=[0.35 * inch, 1.4 * inch, 1.4 * inch, 2.0 * inch, 0.9 * inch, 0.9 * inch],
        repeatRows=1,
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e85d04")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff7ed")]),
            ]
        )
    )
    story.append(t)

    for _, r in loads_df.iterrows():
        story.append(PageBreak())
        load = r.to_dict()
        bol = str(load.get("bol_number") or "—")
        story.append(Paragraph(f"Contract / BOL {bol}".replace("&", "&amp;"), styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))
        detail_rows = [
            ["Field", "Value"],
            ["Shipper", str(load.get("shipper") or "—")],
            ["Commodity", str(load.get("commodity") or "—")],
            ["Weight (tons)", str(load.get("weight_tons") or "—")],
            ["Origin", str(load.get("origin") or "—")],
            ["Destination", str(load.get("destination") or "—")],
            ["Pickup", str(load.get("pickup_date") or "—")],
            ["Delivery", str(load.get("delivery_date") or "—")],
            ["Rate / ton", f"${float(load.get('rate_per_ton') or 0):.2f}"],
            ["Total revenue", f"${float(load.get('total_revenue') or 0):,.2f}"],
            ["Loaded miles", str(load.get("loaded_miles") or load.get("miles") or "—")],
            ["Deadhead miles", str(load.get("deadhead_miles") or "—")],
            ["Status", str(load.get("status") or "—")],
            ["Notes", str(load.get("notes") or "—")[:200]],
        ]
        dt = Table(detail_rows, colWidths=[1.6 * inch, 5.0 * inch])
        dt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1628")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(dt)
        story.append(Spacer(1, 0.3 * inch))
        story.append(
            Paragraph(
                "Shipper: ________________  Driver: ________________  Receiver: ________________",
                styles["Normal"],
            )
        )
        story.append(
            Paragraph(
                "Local-first dispatch record — not a legal contract without signed confirmation.",
                styles["Normal"],
            )
        )

        # Optionally embed note if branded BOL generator available (bytes not merged here)
        _ = bol_pdf_fn

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_all_contracts_zip(
    loads_df: pd.DataFrame,
    bol_pdf_fn: Callable[[dict[str, Any]], bytes],
    *,
    include_audit: bool = True,
    audit_limit: int = 500,
) -> bytes:
    """ZIP of per-load BOL PDFs + contracts summary PDF + full audit log PDF."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        summary = generate_contracts_bundle_pdf(loads_df)
        zf.writestr(f"LP_all_contracts_summary_{date.today().isoformat()}.pdf", summary)

        for _, r in loads_df.iterrows():
            load = r.to_dict()
            bol = str(load.get("bol_number") or f"load_{load.get('id', 'x')}")
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in bol)
            try:
                pdf = bol_pdf_fn(load)
                zf.writestr(f"bols/{safe}.pdf", pdf)
            except Exception as exc:
                zf.writestr(f"bols/{safe}_ERROR.txt", f"BOL generation failed: {exc}")

        if include_audit:
            audit_pdf = generate_audit_log_pdf(limit=audit_limit)
            zf.writestr(f"LP_audit_log_{date.today().isoformat()}.pdf", audit_pdf)

        # Include any BOL PDFs already on disk under attachments/
        if ATTACHMENTS_DIR.is_dir():
            for p in sorted(ATTACHMENTS_DIR.glob("*.pdf"))[:100]:
                try:
                    zf.write(p, arcname=f"attachments/{p.name}")
                except OSError:
                    pass

    buf.seek(0)
    return buf.read()


def write_export_to_attachments(data: bytes, filename: str) -> Path:
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ATTACHMENTS_DIR / filename
    path.write_bytes(data)
    return path
