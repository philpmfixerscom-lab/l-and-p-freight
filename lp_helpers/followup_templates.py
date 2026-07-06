"""SMS/Email follow-up templates — clipboard copy now, Twilio/SMTP later."""

from __future__ import annotations

import json
from typing import Any, Callable

import streamlit as st
import streamlit.components.v1 as components

# Future integration placeholders:
# TWILIO_SEND = os.getenv("TWILIO_ENABLED")  # wire in Settings → SMS Alerts
# SMTP_SEND = os.getenv("SMTP_ENABLED")      # wire for email follow-ups


FOLLOWUP_TEMPLATES: dict[str, dict[str, str]] = {
    "feldspar_discussion": {
        "label": "Feldspar discussion thank-you",
        "channel": "sms",
        "body": (
            "Hi {contact_name}, thank you for the feldspar discussion today. "
            "L & P Freight (39ft end-dump, Spruce Pine NC) is ready for your next "
            "{commodity} load to Central GA. — Phillip / Lawson"
        ),
    },
    "rate_confirmation": {
        "label": "Rate confirmation",
        "channel": "sms",
        "body": (
            "L & P Freight rate confirmation: {commodity} · {weight_tons}t · "
            "{origin} → {destination} · ${rate_per_ton:.2f}/ton · "
            "Total ${total_revenue:,.0f}. BOL {bol_number}. Reply to confirm. — Phillip"
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
            "L & P Freight (Spruce Pine NC, 39ft end-dump) interested at ${rate}. "
            "Can we book? — Phillip {phone}"
        ),
    },
}


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
        "lane": "Spruce Pine NC → Central GA",
        "rate": "$48/ton",
        "phone": "",
    }
    merged = {**defaults, **{k: v for k, v in context.items() if v is not None and v != ""}}
    try:
        return template["body"].format(**merged)
    except (KeyError, ValueError, TypeError):
        return template["body"]


def _clipboard_button(message: str, button_id: str) -> None:
    """Copy message to clipboard via browser JS (local-first, no server send)."""
    escaped = json.dumps(message)
    components.html(
        f"""
        <button id="{button_id}" style="
            width:100%;padding:0.65rem 1rem;background:#e85d04;color:white;
            border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:0.95rem;
        ">📋 Copy to clipboard</button>
        <script>
            document.getElementById("{button_id}").addEventListener("click", function() {{
                navigator.clipboard.writeText({escaped}).then(function() {{
                    document.getElementById("{button_id}").innerText = "✓ Copied!";
                    setTimeout(function() {{
                        document.getElementById("{button_id}").innerText = "📋 Copy to clipboard";
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
) -> None:
    """
    Render follow-up template picker with copy-to-clipboard.
    log_callback(alert_type, message, channel) — optional SMS log hook.
    """
    keys = template_keys or list(FOLLOWUP_TEMPLATES.keys())
    options = {FOLLOWUP_TEMPLATES[k]["label"]: k for k in keys if k in FOLLOWUP_TEMPLATES}

    with st.expander(f"📨 {title}", expanded=False):
        st.caption(
            "Generate message text and copy to your phone or email app. "
            "Future: Twilio SMS / SMTP send from Settings."
        )
        selected_label = st.selectbox(
            "Template",
            list(options.keys()),
            key=f"{panel_key}_template_sel",
        )
        template_key = options[selected_label]
        message = build_followup_message(template_key, context)
        channel = FOLLOWUP_TEMPLATES[template_key]["channel"]

        st.text_area("Message preview", message, height=140, key=f"{panel_key}_preview")
        _clipboard_button(message, f"clip_{panel_key}_{template_key}")

        if log_callback and st.button("Log follow-up (clipboard)", key=f"{panel_key}_log", use_container_width=True):
            log_callback(template_key, message, channel)
            st.success("Follow-up logged locally.")