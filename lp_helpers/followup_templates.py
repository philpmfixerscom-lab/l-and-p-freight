"""SMS/Email templates for rate quotes, follow-ups, and operational messages.

Clipboard copy always works. Optional send callbacks wire Twilio SMS / SMTP
from Alerts tab when secrets are configured.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import streamlit as st
import streamlit.components.v1 as components


FOLLOWUP_TEMPLATES: dict[str, dict[str, str]] = {
    "rate_quote_sms": {
        "label": "Rate quote (SMS)",
        "channel": "sms",
        "body": (
            "L & P FREIGHT | RATE QUOTE\n"
            "{company}\n"
            "{commodity} · {weight_tons}t\n"
            "{origin} → {destination}\n"
            "${rate_per_ton:.2f}/ton · Est. total ${total_revenue:,.0f}\n"
            "39ft end-dump · Spruce Pine NC\n"
            "Valid through {valid_through}. Reply YES to book. — {driver}"
        ),
    },
    "rate_quote_email": {
        "label": "Rate quote (Email)",
        "channel": "email",
        "body": (
            "Subject: L & P Freight — Rate Quote {commodity} {origin} → {destination}\n\n"
            "Hi {contact_name},\n\n"
            "Thank you for the opportunity. L & P Freight is pleased to quote:\n\n"
            "  Commodity:     {commodity}\n"
            "  Weight:        {weight_tons} tons\n"
            "  Lane:          {origin} → {destination}\n"
            "  Rate:          ${rate_per_ton:.2f} per ton\n"
            "  Est. total:    ${total_revenue:,.0f}\n"
            "  Equipment:     39ft / 24-ton frameless lined end-dump\n"
            "  Quote valid:   {valid_through}\n\n"
            "We can cover pickup on {pickup_date} subject to confirmation.\n\n"
            "Reply to this email or call {phone} to book.\n\n"
            "Best regards,\n"
            "{driver}\n"
            "L & P Freight\n"
            "Spruce Pine, NC"
        ),
    },
    "rate_confirmation": {
        "label": "Rate confirmation",
        "channel": "sms",
        "body": (
            "L & P Freight rate confirmation: {commodity} · {weight_tons}t · "
            "{origin} → {destination} · ${rate_per_ton:.2f}/ton · "
            "Total ${total_revenue:,.0f}. BOL {bol_number}. Reply to confirm. — {driver}"
        ),
    },
    "followup_day2": {
        "label": "Follow-up day 2 (no reply)",
        "channel": "sms",
        "body": (
            "Hi {contact_name}, following up on our {commodity} rate quote "
            "({origin} → {destination} @ ${rate_per_ton:.2f}/ton). "
            "Still available this week with the 39ft end-dump. — {driver} / L & P"
        ),
    },
    "followup_week": {
        "label": "Follow-up 1 week",
        "channel": "email",
        "body": (
            "Subject: L & P Freight — Checking in on {commodity} lanes\n\n"
            "Hi {contact_name},\n\n"
            "Wanted to reconnect on {commodity} from {origin} toward {destination}. "
            "Our end-dump is open for the coming week and we keep deadhead low on the "
            "Spruce Pine → Central GA corridor.\n\n"
            "Happy to send a fresh rate if your volumes are moving.\n\n"
            "Best,\n{driver}\nL & P Freight · {phone}"
        ),
    },
    "followup_lost_bid": {
        "label": "Follow-up after lost bid",
        "channel": "sms",
        "body": (
            "Hi {contact_name}, thanks for considering L & P on the recent {commodity} lane. "
            "If anything opens or rates shift, we can move fast with the 39ft end-dump. — {driver}"
        ),
    },
    "feldspar_discussion": {
        "label": "Feldspar discussion thank-you",
        "channel": "sms",
        "body": (
            "Hi {contact_name}, thank you for the feldspar discussion today. "
            "L & P Freight (39ft end-dump, Spruce Pine NC) is ready for your next "
            "{commodity} load to Central GA. — Phillip / Lawson"
        ),
    },
    "pickup_reminder": {
        "label": "Next pickup reminder",
        "channel": "sms",
        "body": (
            "Reminder: L & P Freight scheduled pickup {pickup_date} at {origin}. "
            "Destination {destination} · {commodity}. Please confirm gate/load times. — Lawson"
        ),
    },
    "load_logged_thanks": {
        "label": "Load logged — shipper thanks",
        "channel": "sms",
        "body": (
            "Thank you {company}! Load {bol_number} logged — {commodity} {weight_tons}t "
            "to {destination}. L & P Freight will keep you updated. — Phillip / Lawson"
        ),
    },
    "callback_request": {
        "label": "Callback / lane availability",
        "channel": "email",
        "body": (
            "Subject: L & P Freight — NC/GA end-dump availability\n\n"
            "Hi {contact_name},\n\n"
            "Checking in on {commodity} lanes from Spruce Pine to Central GA. "
            "We run a 39ft / 24-ton frameless end-dump and can cover loads this week.\n\n"
            "Best,\nPhillip / Lawson\nL & P Freight Platform"
        ),
    },
    "bulkloads_opportunity": {
        "label": "BulkLoads opportunity follow-up",
        "channel": "sms",
        "body": (
            "Hi, saw your {commodity} load on BulkLoads — {lane}. "
            "L & P Freight (Spruce Pine NC, 39ft end-dump) interested at {rate}. "
            "Can we book? — Phillip {phone}"
        ),
    },
    "scale_ticket_request": {
        "label": "Scale ticket request",
        "channel": "sms",
        "body": (
            "L & P Freight — please send scale ticket photo for BOL {bol_number} "
            "({commodity} · {weight_tons}t). Reply with photo or email. — {driver}"
        ),
    },
}


# Keys most useful for quote / sales follow-up workflows
RATE_QUOTE_KEYS = [
    "rate_quote_sms",
    "rate_quote_email",
    "rate_confirmation",
    "followup_day2",
    "followup_week",
    "followup_lost_bid",
]


def list_templates(channel: str | None = None) -> dict[str, dict[str, str]]:
    if not channel:
        return dict(FOLLOWUP_TEMPLATES)
    ch = channel.lower()
    return {k: v for k, v in FOLLOWUP_TEMPLATES.items() if v.get("channel") == ch}


def parse_email_template(body: str) -> tuple[str, str]:
    """Split 'Subject: ...\\n\\nbody' into (subject, body)."""
    m = re.match(r"^Subject:\s*(.+?)\n\n([\s\S]*)$", body.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "L & P Freight", body.strip()


def build_followup_message(template_key: str, context: dict[str, Any]) -> str:
    """Format a follow-up template with safe defaults for missing fields."""
    template = FOLLOWUP_TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Unknown template: {template_key}")

    defaults: dict[str, Any] = {
        "contact_name": "there",
        "company": "Shipper",
        "commodity": "Feldspar",
        "weight_tons": 24,
        "origin": "Spruce Pine, NC",
        "destination": "Central Georgia (Kohler area)",
        "rate_per_ton": 48.0,
        "total_revenue": 1152.0,
        "bol_number": "LP-DRAFT",
        "pickup_date": "TBD",
        "valid_through": "end of week",
        "lane": "Spruce Pine NC → Central GA",
        "rate": "$48/ton",
        "phone": "",
        "driver": "Phillip / Lawson",
        "shipper": "Shipper",
    }
    # Coerce numeric fields so format specs do not explode
    merged = {**defaults}
    for k, v in context.items():
        if v is None or v == "":
            continue
        if k in ("rate_per_ton", "total_revenue", "weight_tons"):
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                merged[k] = defaults[k]
        else:
            merged[k] = v
    if not merged.get("company") and merged.get("shipper"):
        merged["company"] = merged["shipper"]
    try:
        return template["body"].format(**merged)
    except (KeyError, ValueError, TypeError):
        # Best-effort: replace known tokens only
        body = template["body"]
        for k, v in merged.items():
            body = body.replace("{" + k + "}", str(v))
        return re.sub(r"\{[^}]+\}", "", body)


def _clipboard_button(message: str, button_id: str) -> None:
    """Copy message to clipboard via browser JS (local-first, no server send)."""
    escaped = json.dumps(message)
    safe_id = re.sub(r"[^\w\-]", "_", button_id)
    components.html(
        f"""
        <button id="{safe_id}" style="
            width:100%;padding:0.65rem 1rem;background:#e85d04;color:white;
            border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:0.95rem;
        ">📋 Copy to clipboard</button>
        <script>
            document.getElementById("{safe_id}").addEventListener("click", function() {{
                navigator.clipboard.writeText({escaped}).then(function() {{
                    document.getElementById("{safe_id}").innerText = "✓ Copied!";
                    setTimeout(function() {{
                        document.getElementById("{safe_id}").innerText = "📋 Copy to clipboard";
                    }}, 2000);
                }});
            }});
        </script>
        """,
        height=52,
    )


def render_followup_panel(
    title: str,
    context: dict[str, Any],
    template_keys: list[str] | None = None,
    log_callback: Callable[[str, str, str], None] | None = None,
    panel_key: str = "followup",
    send_sms: Callable[[str, str], str | None] | None = None,
    send_email: Callable[[str, str, str], None] | None = None,
    default_phone: str = "",
    default_email: str = "",
) -> None:
    """
    Template picker with copy-to-clipboard and optional Twilio/SMTP send.

    log_callback(alert_type, message, channel)
    send_sms(to_number, body) -> optional sid
    send_email(to_email, subject, body)
    """
    keys = template_keys or list(FOLLOWUP_TEMPLATES.keys())
    options = {FOLLOWUP_TEMPLATES[k]["label"]: k for k in keys if k in FOLLOWUP_TEMPLATES}
    if not options:
        st.warning("No templates available.")
        return

    with st.expander(f"📨 {title}", expanded=False):
        st.caption(
            "Rate quotes & follow-ups — copy to clipboard, or send via Twilio / SMTP "
            "when configured in secrets.toml."
        )
        selected_label = st.selectbox(
            "Template",
            list(options.keys()),
            key=f"{panel_key}_template_sel",
        )
        template_key = options[selected_label]
        message = build_followup_message(template_key, context)
        channel = FOLLOWUP_TEMPLATES[template_key]["channel"]

        st.text_area("Message preview", message, height=160, key=f"{panel_key}_preview")
        st.caption(f"Channel: **{channel.upper()}** · template `{template_key}`")
        _clipboard_button(message, f"clip_{panel_key}_{template_key}")

        c1, c2, c3 = st.columns(3)
        if log_callback and c1.button(
            "Log locally", key=f"{panel_key}_log", use_container_width=True
        ):
            log_callback(template_key, message, channel)
            st.success("Follow-up logged locally.")

        if channel == "sms" and send_sms:
            phone = c2.text_input(
                "SMS to",
                value=default_phone or str(context.get("phone") or ""),
                key=f"{panel_key}_sms_to",
            )
            if c3.button("Send SMS", key=f"{panel_key}_sms_send", use_container_width=True, type="primary"):
                if not phone.strip():
                    st.error("Enter a phone number (E.164 preferred).")
                else:
                    try:
                        sid = send_sms(phone.strip(), message)
                        if log_callback:
                            log_callback(template_key, message, "twilio")
                        st.success(f"SMS sent{f' · {sid}' if sid else ''}.")
                    except Exception as exc:
                        st.error(f"SMS failed: {exc}")
        elif channel == "email" and send_email:
            to_addr = c2.text_input(
                "Email to",
                value=default_email or str(context.get("email") or ""),
                key=f"{panel_key}_email_to",
            )
            if c3.button(
                "Send email",
                key=f"{panel_key}_email_send",
                use_container_width=True,
                type="primary",
            ):
                if not to_addr.strip():
                    st.error("Enter an email address.")
                else:
                    try:
                        subject, body = parse_email_template(message)
                        send_email(to_addr.strip(), subject, body)
                        if log_callback:
                            log_callback(template_key, message, "smtp")
                        st.success("Email sent.")
                    except Exception as exc:
                        st.error(f"Email failed: {exc}")
