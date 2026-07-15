"""Branded Bill of Lading PDF export for L & P Freight Platform."""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def bol_pdf_filename(load: dict[str, Any]) -> str:
    """Auto-generate filename: L&P_BOL_[LoadID]_[Date].pdf"""
    load_id = load.get("bol_number") or load.get("id") or "DRAFT"
    safe_id = str(load_id).replace("/", "-").replace(" ", "_")
    pickup = load.get("pickup_date") or str(date.today())
    try:
        date_str = str(pickup)[:10].replace("-", "")
    except (TypeError, ValueError):
        date_str = date.today().strftime("%Y%m%d")
    return f"L&P_BOL_{safe_id}_{date_str}.pdf"


def generate_branded_bol_pdf(
    load: dict[str, Any],
    *,
    app_version: str = "3.0",
    trailer_profile: str = "39ft / 24-ton Frameless lined end-dump",
    primary_origin: str = "Spruce Pine, NC",
) -> bytes:
    """Professional printable BOL with L & P header, logo placeholder, and signature lines."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.45 * inch, bottomMargin=0.45 * inch)
    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle(
        "BrandTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#e85d04"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "BrandSub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#1e3a5f"),
        spaceAfter=10,
    )
    normal = styles["Normal"]
    story: list[Any] = []

    # Logo placeholder + branded header
    logo_row = [
        [
            Paragraph(
                '<font size="28" color="#e85d04"><b>L&amp;P</b></font>',
                styles["Normal"],
            ),
            Paragraph(
                "<b>L &amp; P FREIGHT PLATFORM</b><br/>"
                f"<font size='9'>Bill of Lading · Spruce Pine NC · v{app_version}</font>",
                brand_style,
            ),
        ]
    ]
    logo_table = Table(logo_row, colWidths=[1.2 * inch, 5.5 * inch])
    logo_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (0, 0), 1.5, colors.HexColor("#e85d04")),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#fff7ed")),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
    ]))
    story.append(logo_table)
    story.append(Paragraph(f"<i>{trailer_profile}</i>", subtitle_style))
    story.append(Spacer(1, 0.15 * inch))

    header_data = [
        ["BOL #", load.get("bol_number", "—"), "Date", load.get("pickup_date", str(date.today()))],
        ["Shipper", load.get("shipper", "—"), "Commodity", load.get("commodity", "—")],
        ["Origin", load.get("origin", primary_origin), "Destination", load.get("destination", "—")],
        ["Weight (tons)", str(load.get("weight_tons", "—")), "Miles", str(load.get("miles", "—"))],
        ["Loaded Miles", str(load.get("loaded_miles", "—")), "Rate/Ton", f"${float(load.get('rate_per_ton', 0)):.2f}"],
        ["Total Revenue", f"${float(load.get('total_revenue', 0)):,.2f}", "Status", str(load.get("status", "Logged"))],
    ]
    detail_table = Table(header_data, colWidths=[1.3 * inch, 2.2 * inch, 1.3 * inch, 2.2 * inch])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1628")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 0.25 * inch))

    if load.get("notes"):
        story.append(Paragraph(f"<b>Notes:</b> {load['notes']}", normal))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(
        "<b>Special Instructions:</b> Cargo must be covered and secured per FMCSA load securement rules. "
        "Lined end-dump — suitable for fines and bulk mineral loads (feldspar, mica, clay, spar).",
        normal,
    ))
    story.append(Spacer(1, 0.4 * inch))

    sig_data = [
        ["Shipper Signature", "", "Date", ""],
        ["", "", "", ""],
        ["Driver Signature (L & P)", "", "Date", ""],
        ["", "", "", ""],
        ["Receiver / Consignee Signature", "", "Date", ""],
        ["", "", "", ""],
    ]
    sig_table = Table(sig_data, colWidths=[2.0 * inch, 2.8 * inch, 0.7 * inch, 1.5 * inch])
    sig_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (1, 1), (1, 1), 1, colors.black),
        ("LINEBELOW", (3, 1), (3, 1), 1, colors.black),
        ("LINEBELOW", (1, 3), (1, 3), 1, colors.black),
        ("LINEBELOW", (3, 3), (3, 3), 1, colors.black),
        ("LINEBELOW", (1, 5), (1, 5), 1, colors.black),
        ("LINEBELOW", (3, 5), (3, 5), 1, colors.black),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "<font size='8' color='#64748b'>L &amp; P Freight Platform · Phillip / Lawson · "
        "Local-first dispatch · Not a legal contract without signed confirmation.</font>",
        normal,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()