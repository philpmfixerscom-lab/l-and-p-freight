"""
L & P Freight Platform.
Dispatch OS for owner-operators and small bulk fleets — loaded miles, rates, BOLs, cab view.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd
import streamlit as st
from fpdf import FPDF

try:
    import plotly.express as px
except ImportError:
    px = None  # type: ignore[assignment]

try:
    import smtplib
    from email.mime.text import MIMEText
except ImportError:
    smtplib = None  # type: ignore[assignment]
    MIMEText = None  # type: ignore[assignment,misc]

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    import folium
    from streamlit_folium import st_folium

    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

log = logging.getLogger("lawson_freight")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lp_dispatch.db"
ATTACHMENTS_DIR = BASE_DIR / "attachments"
BACKUP_DIR = BASE_DIR / "backups"
APP_VERSION = "4.4"
TRAILER_MAX_TONS = 24
APPROVED_COMMODITIES = [
    "Feldspar", "Mica", "Spar", "Clay", "Rock",
    "Lime", "Fertilizer", "Sand", "Gravel", "Aggregate", "Other",
]
TARGET_LANE_ORIGIN = "Spruce Pine, NC"
TARGET_LANE_DESTINATION = "Central Georgia (Kohler area)"
DEFAULT_LANE_MILES = 285

try:
    from lp_helpers.lawson_profile import (
        CARRIER_NAME,
        DEFAULT_OWNER,
        OWNERS,
        HIGHWAY_CORRIDORS,
        LAWSON_GEOFENCES,
        LAWSON_SEED_LEADS,
        LAWSON_SIM_ROUTE,
        LOADED_MILE_TARGET,
        MISSION_BLURB,
        PAGE_TITLE,
        PLATFORM_TITLE,
        PRIMARY_RECEIVER,
        TAGLINE,
        TRAILER_DESC,
        TRUCK_LABEL,
    )
except ImportError:
    CARRIER_NAME = "L & P Freight"
    PLATFORM_TITLE = "L & P Freight Platform"
    PAGE_TITLE = "L & P Freight"
    TAGLINE = "Paid miles north. Empty miles never."
    MISSION_BLURB = (
        "When the outbound pays but the return doesn't, small fleets bleed cash. "
        "Track loaded vs empty, score homebound returns, quote by the ton, update from the cab."
    )
    DEFAULT_OWNER = "Phillip"
    OWNERS = ("Phillip", "Lawson")
    TRUCK_LABEL = "L&P End-Dump"
    TRAILER_DESC = "39ft Frameless End-Dump"
    HIGHWAY_CORRIDORS = "Hwy 19E & 226"
    LOADED_MILE_TARGET = 0.80
    PRIMARY_RECEIVER = "Kohler Co."
    LAWSON_SIM_ROUTE = [
        (35.912, -82.064, "Spruce Pine, NC"),
        (35.650, -82.450, "Asheville corridor"),
        (35.200, -82.800, "I-26 southbound"),
        (34.500, -83.200, "Atlanta outskirts"),
        (33.447, -83.809, "Central Georgia (Kohler area)"),
    ]
    LAWSON_GEOFENCES = [
        ("Spruce Pine Yard", 35.912, -82.064, 0.8),
        ("Kohler Central GA", 32.98, -82.72, 5.0),
    ]
    LAWSON_SEED_LEADS = []

TAB_LABELS = [
    "📊 Dashboard",
    "👥 Leads",
    "📝 Logger",
    "📦 Board",
    "🗺️ GPS",
    "📄 BOL",
    "📲 Alerts",
]
TAB_KEYS = ["Dashboard", "Leads", "Logger", "Board", "GPS", "BOL", "Alerts"]

FILTER_DEFAULTS: dict[str, str] = {
    "filter_leads_status": "All",
    "filter_loads_status": "All",
    "filter_leads_search": "",
    "filter_loads_search": "",
    "gps_live_sim": "1",
    "sms_auto_send": "0",
    "sms_auto_new_load": "1",
}

SIM_ROUTE: list[tuple[float, float, str]] = LAWSON_SIM_ROUTE

SMS_TEMPLATES: dict[str, str] = {
    "arrival": (
        "L & P FREIGHT | ARRIVAL\n"
        "{company}\n"
        "On site: {location}\n"
        "Owner: {driver} · 39ft end-dump\n"
        "Reply STOP to opt out."
    ),
    "load update": (
        "L & P FREIGHT | LOAD UPDATE\n"
        "{company}\n"
        "{detail}\n"
        "Spruce Pine NC → Central GA\n"
        "Reply STOP to opt out."
    ),
    "departure": (
        "L & P FREIGHT | DEPARTURE\n"
        "{company}\n"
        "Departing: {location}\n"
        "ETA per BOL · {driver}\n"
        "Reply STOP to opt out."
    ),
    "rate_confirmation": (
        "L & P FREIGHT | RATE CONFIRMED\n"
        "{company}\n"
        "{commodity} · {weight_tons:.1f}t\n"
        "{origin} → {destination}\n"
        "${rate_per_ton:.2f}/ton · Total ${total_revenue:,.0f}\n"
        "BOL {bol_number}\n"
        "Reply STOP to opt out."
    ),
    "status_dispatched": (
        "L & P FREIGHT | DISPATCHED\n"
        "BOL {bol_number}\n"
        "{commodity} · {weight_tons:.1f}t to {destination}\n"
        "GPS tracking active. — {driver}"
    ),
    "bol_ready": (
        "L & P FREIGHT | BOL READY\n"
        "BOL {bol_number} generated for {shipper}\n"
        "{commodity} · {weight_tons:.1f}t\n"
        "Pickup {pickup_date} · {origin} → {destination}"
    ),
    "new_load_logged": (
        "L & P FREIGHT | NEW LOAD\n"
        "{shipper} · {commodity} · {weight_tons:.1f}t\n"
        "BOL {bol_number} · {status}\n"
        "{origin} → {destination}"
    ),
}

F = TypeVar("F", bound=Callable[..., Any])


def safe_ui(label: str = "Operation") -> Callable[[F], F]:
    """Wrap UI handlers — show friendly Streamlit errors, log details."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except sqlite3.Error as exc:
                log.exception("%s database error", label)
                st.error(f"{label} failed — database error. Check lp_dispatch.db permissions.")
                st.caption(str(exc))
            except Exception as exc:
                log.exception("%s unexpected error", label)
                st.error(f"{label} failed — {type(exc).__name__}: {exc}")
            return None

        return wrapper  # type: ignore[return-value]

    return decorator


def get_secret(section: str, key: str, default: str = "") -> str:
    """Read credential from .streamlit/secrets.toml, then app_settings fallback."""
    try:
        val = st.secrets[section][key]
        if val:
            return str(val).strip()
    except Exception:
        pass
    try:
        from lp_helpers.database import get_setting

        return get_setting(f"{section}_{key}", default).strip()
    except ImportError:
        return _local_get_setting(f"{section}_{key}", default).strip()


def _local_get_setting(key: str, default: str = "") -> str:
    try:
        with closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row and row["value"] is not None else default
    except Exception:
        return default


def _local_set_setting(key: str, value: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, value),
        )
        conn.commit()


def persist_setting(key: str, value: str) -> None:
    try:
        from lp_helpers.database import set_setting

        set_setting(key, value)
    except ImportError:
        _local_set_setting(key, value)


def get_active_owner() -> str:
    """Get current owner with safe fallback (session → helper → DB → default)."""
    try:
        if "owner_role" in st.session_state:
            role = st.session_state["owner_role"]
            if role in OWNERS:
                return role

        try:
            from lp_helpers.ui_components import get_owner_role

            role = get_owner_role()
            if role in OWNERS:
                st.session_state["owner_role"] = role
                return role
        except Exception:
            pass

        role = _local_get_setting("owner_role", DEFAULT_OWNER)
        if role in OWNERS:
            st.session_state["owner_role"] = role
            return role
    except Exception:
        pass

    return DEFAULT_OWNER


def set_active_owner(role: str) -> None:
    """Safely set and persist the active owner with error handling."""
    if role not in OWNERS:
        try:
            st.warning(f"Invalid owner role: {role}")
        except Exception:
            pass
        return

    try:
        from lp_helpers.ui_components import set_owner_role

        set_owner_role(role)
    except ImportError:
        try:
            _local_set_setting("owner_role", role)
        except Exception as exc:
            try:
                st.error(f"Failed to persist owner role: {exc}")
            except Exception:
                pass
            st.session_state["owner_role"] = role
            return
    except Exception as exc:
        try:
            st.error(f"Failed to persist owner role: {exc}")
        except Exception:
            pass
        try:
            _local_set_setting("owner_role", role)
        except Exception:
            pass

    st.session_state["owner_role"] = role


def load_persistent_filters() -> None:
    for key, default in FILTER_DEFAULTS.items():
        if key not in st.session_state:
            try:
                from lp_helpers.database import get_setting

                st.session_state[key] = get_setting(key, default) or default
            except ImportError:
                st.session_state[key] = _local_get_setting(key, default) or default


def save_filter(key: str, value: str) -> None:
    st.session_state[key] = value
    persist_setting(key, value)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.strip().startswith("+"):
        return raw.strip()
    return raw.strip()


def format_sms(template_key: str, context: dict[str, Any]) -> str:
    template = SMS_TEMPLATES.get(template_key, SMS_TEMPLATES["load update"])
    defaults: dict[str, Any] = {
        "company": "Contact",
        "location": PRIMARY_LANE["origin"],
        "detail": "Status update",
        "commodity": "Bulk",
        "weight_tons": 0.0,
        "origin": PRIMARY_LANE["origin"],
        "destination": PRIMARY_LANE["destination"],
        "rate_per_ton": 0.0,
        "total_revenue": 0.0,
        "bol_number": "DRAFT",
        "shipper": "Shipper",
        "pickup_date": str(date.today()),
    }
    defaults.update(context)
    if "driver" not in defaults:
        defaults["driver"] = get_active_owner()
    try:
        return template.format(**defaults)
    except (KeyError, ValueError) as exc:
        log.warning("SMS template format error: %s", exc)
        return f"L & P FREIGHT: {defaults.get('detail', 'Update')} — {get_active_owner()}"


EMAIL_TEMPLATES: dict[str, str] = {
    "arrival": (
        "L & P FREIGHT — Arrival Notice\n\n"
        "Company: {company}\n"
        "On site: {location}\n"
        "Owner: Phillip · 39ft frameless end-dump\n"
        "Lane: Spruce Pine NC → Central GA"
    ),
    "load update": (
        "L & P FREIGHT — Load Update\n\n"
        "Company: {company}\n"
        "{detail}\n"
        "Spruce Pine NC → Central Georgia"
    ),
    "rate_confirmation": (
        "L & P FREIGHT — Rate Confirmed\n\n"
        "Company: {company}\n"
        "{commodity} · {weight_tons:.1f} tons\n"
        "{origin} → {destination}\n"
        "${rate_per_ton:.2f}/ton · Total ${total_revenue:,.0f}\n"
        "BOL {bol_number}"
    ),
    "bol_ready": (
        "L & P FREIGHT — BOL Ready\n\n"
        "BOL {bol_number} for {shipper}\n"
        "{commodity} · {weight_tons:.1f} tons\n"
        "Pickup {pickup_date} · {origin} → {destination}"
    ),
}


def format_email(template_key: str, context: dict[str, Any]) -> tuple[str, str]:
    """Return (subject, body) for an email template."""
    body_template = EMAIL_TEMPLATES.get(template_key, EMAIL_TEMPLATES["load update"])
    defaults: dict[str, Any] = {
        "company": "Contact",
        "location": PRIMARY_LANE["origin"],
        "detail": "Status update",
        "commodity": "Bulk",
        "weight_tons": 0.0,
        "origin": PRIMARY_LANE["origin"],
        "destination": PRIMARY_LANE["destination"],
        "rate_per_ton": 0.0,
        "total_revenue": 0.0,
        "bol_number": "DRAFT",
        "shipper": "Shipper",
        "pickup_date": str(date.today()),
    }
    defaults.update(context)
    subject = f"L & P Freight — {template_key.replace('_', ' ').title()}"
    try:
        return subject, body_template.format(**defaults)
    except (KeyError, ValueError) as exc:
        log.warning("Email template format error: %s", exc)
        return subject, f"L & P FREIGHT update — {defaults.get('detail', 'Status')}"


def send_email_notification(to_email: str, subject: str, body: str) -> None:
    if not smtplib or not MIMEText:
        raise ImportError("smtplib unavailable")
    host = get_secret("smtp", "host")
    port = int(get_secret("smtp", "port", "587") or "587")
    user = get_secret("smtp", "user")
    password = get_secret("smtp", "password")
    from_addr = get_secret("smtp", "from_email", user)
    if not all([host, user, password, from_addr]):
        raise ValueError(
            "SMTP credentials missing — add [smtp] section to .streamlit/secrets.toml"
        )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email.strip()
    with smtplib.SMTP(host, port, timeout=12) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_email.strip()], msg.as_string())


def send_twilio_notification(to_number: str, body: str) -> str:
    sid = get_secret("twilio", "account_sid")
    token = get_secret("twilio", "auth_token")
    from_num = get_secret("twilio", "from_number")
    if not all([sid, token, from_num]):
        raise ValueError(
            "Twilio credentials missing — add [twilio] section to .streamlit/secrets.toml"
        )
    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise ImportError("Install twilio: pip install twilio") from exc
    client = Client(sid, token)
    msg = client.messages.create(body=body, from_=from_num, to=normalize_phone(to_number))
    return str(msg.sid)


def log_sms_event(
    lead_id: int | None,
    alert_type: str,
    message: str,
    sent_via: str = "clipboard",
    twilio_sid: str | None = None,
) -> None:
    try:
        from lp_helpers.engines import log_sms

        log_sms(lead_id, alert_type, message, sent_via, twilio_sid)
        return
    except ImportError:
        pass
    with closing(get_connection()) as conn:
        conn.execute(
            """
            INSERT INTO sms_log (lead_id, alert_type, message, sent_via, twilio_sid)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, alert_type, message, sent_via, twilio_sid),
        )
        conn.commit()


def dispatch_emergency(
    emergency_key: str,
    message: str,
    context: dict[str, Any],
) -> tuple[bool, str]:
    """Log incident and annotate active load — no personal SMS; owners call official numbers."""
    log_sms_event(None, f"emergency_{emergency_key}", message, "emergency")

    load_noted = False
    try:
        with closing(get_connection()) as conn:
            row = conn.execute(
                """
                SELECT id FROM loads
                WHERE status IN ('Dispatched', 'In Transit', 'Booked')
                ORDER BY pickup_date DESC LIMIT 1
                """
            ).fetchone()
            if row:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                note = f"\n[{stamp}] EMERGENCY {emergency_key}: {context.get('detail', '')}"
                conn.execute(
                    "UPDATE loads SET notes = COALESCE(notes, '') || ? WHERE id = ?",
                    (note, row["id"]),
                )
                conn.commit()
                load_noted = True
    except Exception as exc:
        log.warning("Emergency load note failed: %s", exc)

    if load_noted:
        return True, "Incident logged on active load. Call official numbers above if you have not already."
    return True, "Incident logged. Call official numbers above if you have not already."


def _render_emergency_controls(
    *,
    load: dict[str, Any] | None = None,
    gps_fix: dict[str, Any] | None = None,
    key_prefix: str = "dispatch_em",
    compact: bool = False,
) -> None:
    from lp_helpers.emergency_alerts import render_emergency_panel

    if load is None:
        loads_df = fetch_loads()
        if not loads_df.empty:
            active = loads_df[
                loads_df["status"].astype(str).isin(["Dispatched", "In Transit", "Booked"])
            ]
            load = active.iloc[0].to_dict() if not active.empty else loads_df.iloc[0].to_dict()
        else:
            load = {}

    render_emergency_panel(
        driver=get_active_owner(),
        truck_label=TRUCK_LABEL,
        load=load,
        gps_fix=gps_fix,
        on_dispatch=lambda k, m, c: dispatch_emergency(k, m, c),
        compact=compact,
        key_prefix=key_prefix,
    )


def maybe_auto_notify_load(load: dict[str, Any], lead_phone: str | None) -> None:
    if get_secret("twilio", "auto_send", "0") != "1" and st.session_state.get("sms_auto_send") != "1":
        return
    if not lead_phone:
        return
    status = str(load.get("status", ""))
    if status not in ("Dispatched", "In Transit"):
        return
    body = format_sms("status_dispatched", load)
    try:
        tw_sid = send_twilio_notification(lead_phone, body)
        log_sms_event(None, "status_dispatched", body, "twilio", tw_sid)
    except Exception as exc:
        log.warning("Auto SMS skipped: %s", exc)


def notify_dispatcher_new_load(load: dict[str, Any]) -> None:
    auto_on = (
        st.session_state.get("sms_auto_new_load", "1") == "1"
        or get_secret("twilio", "auto_send_new_load", "1") == "1"
    )
    if not auto_on:
        return
    dispatch_phone = get_secret("twilio", "dispatch_phone", "+18284678218")
    if not dispatch_phone.strip():
        return
    body = format_sms("new_load_logged", load)
    try:
        tw_sid = send_twilio_notification(dispatch_phone, body)
        log_sms_event(None, "new_load_logged", body, "twilio", tw_sid)
    except Exception as exc:
        log.warning("Dispatcher new-load SMS skipped: %s", exc)


def _traccar_connection_params() -> tuple[str, str, str, str]:
    url = st.session_state.get(
        "traccar_url_input",
        get_secret("traccar", "url", "http://localhost:8082"),
    )
    token = st.session_state.get(
        "traccar_api_key_input",
        get_secret("traccar", "api_token", ""),
    )
    email = get_secret("traccar", "email", "admin")
    password = get_secret("traccar", "password", "admin")
    return url.strip(), token.strip(), email, password


def get_traccar_live() -> Any:
    from lp_helpers.traccar_live import TraccarLive

    url, token, email, password = _traccar_connection_params()
    return TraccarLive(
        get_secret=get_secret,
        url=url,
        api_token=token,
        email=email,
        password=password,
    )


@st.cache_data(ttl=20, show_spinner=False)
def _cached_traccar_fleet(
    url: str, token: str, email: str, password: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    from lp_helpers.traccar_live import TraccarLive

    client = TraccarLive(
        get_secret=get_secret,
        url=url,
        api_token=token,
        email=email,
        password=password,
    )
    status = client.connection_status()
    if not status.get("ok"):
        return status, [], []
    return status, client.fetch_fleet(), client.fetch_devices()


def clear_traccar_cache() -> None:
    _cached_traccar_fleet.clear()


def interpolate_route(progress: float) -> tuple[float, float, str]:
    """Return lat, lon, label along SIM_ROUTE for progress 0..1."""
    progress = max(0.0, min(1.0, progress))
    segments = len(SIM_ROUTE) - 1
    pos = progress * segments
    idx = min(int(pos), segments - 1)
    frac = pos - idx
    lat1, lon1, label1 = SIM_ROUTE[idx]
    lat2, lon2, label2 = SIM_ROUTE[idx + 1]
    lat = lat1 + (lat2 - lat1) * frac
    lon = lon1 + (lon2 - lon1) * frac
    label = label2 if frac > 0.5 else label1
    return lat, lon, label


def inject_elite_dark_css() -> None:
    """High-contrast dark mode overrides on top of lp_helpers theme."""
    st.markdown(
        """
        <style>
        :root {
            --lf-bg: #0a0e14;
            --lf-card: #151d2b;
            --lf-text: #f8fafc;
            --lf-muted: #b8c5d9;
            --lf-border: #3d5270;
            --lf-orange: #ff8c42;
            --lf-green: #5eead4;
            --lf-blue: #7dd3fc;
            --lf-red: #fb7185;
            --lf-sidebar: #060a10;
            --lf-shadow: rgba(0,0,0,0.35);
        }
        .stApp { background: var(--lf-bg) !important; }
        div[data-testid="stMetric"] label { color: var(--lf-muted) !important; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: var(--lf-text) !important;
        }
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox > div > div {
            background: var(--lf-card) !important;
            color: var(--lf-text) !important;
            border-color: var(--lf-border) !important;
        }
        .stDataFrame { border: 1px solid var(--lf-border); border-radius: 10px; }
        .lf-gps-badge {
            display: inline-block; padding: 0.25rem 0.65rem; border-radius: 20px;
            font-size: 0.75rem; font-weight: 700; margin-right: 0.5rem;
        }
        .lf-gps-badge.live { background: rgba(94,234,212,0.15); color: var(--lf-green); }
        .lf-gps-badge.sim { background: rgba(251,146,60,0.15); color: var(--lf-orange); }
        </style>
        """,
        unsafe_allow_html=True,
    )

TARGET_LANE_ORIGIN = "Spruce Pine, NC"
TARGET_LANE_DESTINATION = "Central Georgia (Kohler area)"

PRIMARY_LANE = {
    "origin": TARGET_LANE_ORIGIN,
    "destination": TARGET_LANE_DESTINATION,
    "loaded_miles": 285,
    "baseline_rate_per_ton": 48.0,
}

TRAILER_MAX_TONS = 24
DEFAULT_LANE_MILES = 285
FUEL_COST_PER_MILE = 0.72
OPS_COST_PER_MILE = 0.18
DEFAULT_DEADHEAD_MILES = 285

LOAD_STATUS_OPTIONS = [
    "Potential",
    "Quoted",
    "Booked",
    "Logged",
    "Dispatched",
    "In Transit",
    "Delivered",
    "Paid",
]

HIGH_FIT_COMMODITIES = {
    "feldspar", "quartz", "mica", "kaolin", "silica sand", "spar", "clay",
    "industrial minerals", "aggregate", "crushed stone", "rock", "sand", "gravel",
}
MEDIUM_FIT_COMMODITIES = {"lime", "fertilizer", "kaolin"}
LOW_FIT_KEYWORDS = {
    "glass", "crushed glass", "slag", "hot", "liquid", "wet concrete",
    "asphalt", "hazmat", "corrosive", "steel", "rebar", "poultry litter",
}
WASHOUT_KEYWORDS = {"glass", "crushed glass", "slag", "asphalt", "fertilizer", "lime"}

APPROVED_COMMODITIES = [
    "Feldspar",
    "Quartz",
    "Mica",
    "Kaolin",
    "Silica Sand",
    "Industrial Minerals",
    "Aggregate",
    "Crushed Stone",
    "Spar",
    "Clay",
    "Rock",
    "Lime",
    "Fertilizer",
    "Other",
]

LEAD_STATUS_OPTIONS = [
    "New",
    "Contacted",
    "Quoted",
    "Hot",
    "Active",
    "Negotiating",
    "Closed",
]

CALL_TYPES = ["Outbound", "Inbound", "Follow-up", "Rate Quote"]
CALL_OUTCOMES = [
    "No answer",
    "Left voicemail",
    "Spoke — load offered",
    "Spoke — no load",
    "Callback scheduled",
]

SEED_LEADS = LAWSON_SEED_LEADS or []


def render_section_header(title: str, icon: str = "") -> None:
    """Reusable section header with optional icon."""
    st.markdown(
        f"""
        <div style="
            display:flex;
            align-items:center;
            gap:10px;
            margin:20px 0 12px 0;
        ">
            <h2 style="
                margin:0;
                font-size:1.35rem;
                font-weight:700;
            ">
                {icon} {title}
            </h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_load_inputs(
    shipper: str,
    commodity: str,
    weight: float,
    rate_per_ton: float,
    total_revenue: float,
    pricing_mode: str,
) -> list[str]:
    errors = []
    if not shipper or not str(shipper).strip():
        errors.append("Shipper is required.")
    if not commodity or not str(commodity).strip():
        errors.append("Commodity is required.")
    if weight is None or weight <= 0:
        errors.append("Weight must be greater than zero.")
    if weight > TRAILER_MAX_TONS:
        errors.append(f"Weight exceeds {TRAILER_MAX_TONS}-ton trailer limit.")
    if pricing_mode == "Rate per ton" and (rate_per_ton is None or rate_per_ton <= 0):
        errors.append("Enter a valid rate per ton.")
    if pricing_mode == "Total revenue" and (total_revenue is None or total_revenue <= 0):
        errors.append("Enter a valid total revenue.")
    return errors


def validate_bol_load(load: dict[str, Any]) -> list[str]:
    errors = []
    if not load.get("bol_number"):
        errors.append("Load is missing a BOL number.")
    if not load.get("shipper"):
        errors.append("Load is missing a shipper.")
    if not load.get("commodity"):
        errors.append("Load is missing a commodity.")
    if not load.get("weight_tons") or float(load.get("weight_tons", 0)) <= 0:
        errors.append("Load has invalid weight.")
    return errors


# ---------------------------------------------------------------------------
# Auto-backup
# ---------------------------------------------------------------------------

def auto_backup_db() -> None:
    try:
        if not DB_PATH.exists():
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"lp_dispatch_{stamp}.db"
        shutil.copy2(DB_PATH, dest)
        log.info("Auto-backup created: %s", dest)
    except Exception as exc:
        log.warning("Auto-backup skipped: %s", exc)


# ---------------------------------------------------------------------------
# DB init + seed
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lane_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT,
            destination TEXT,
            commodity TEXT,
            base_rate_per_ton REAL,
            typical_distance_miles INTEGER,
            notes TEXT
        )
        """
    )

    for lead in SEED_LEADS:
        existing = cursor.execute(
            "SELECT id FROM leads WHERE company = ?",
            (lead["company"],),
        ).fetchone()
        if existing is None:
            cursor.execute(
                """
                INSERT INTO leads
                    (company, contact_name, phone, email, commodity_focus, lane_notes,
                     status, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    lead["company"],
                    lead.get("contact_name", "Dispatch"),
                    lead.get("phone", ""),
                    lead.get("email", ""),
                    lead["commodity_focus"],
                    lead["lane_notes"],
                    lead["status"],
                    lead["priority"],
                ),
            )

    conn.commit()
    conn.close()


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_leads_cached(tenant_id: str) -> pd.DataFrame:
    """Cached leads (60s) — tenant-scoped."""
    from lp_helpers.repositories.leads import list_leads

    with closing(get_connection()) as conn:
        return list_leads(conn, tenant_id=tenant_id)


def fetch_leads() -> pd.DataFrame:
    """Leads for current tenant (cache key = tenant_id)."""
    try:
        from lp_helpers.tenancy import current_tenant_id

        return _fetch_leads_cached(current_tenant_id())
    except Exception as exc:
        log.exception("fetch_leads failed")
        st.error(f"Could not load leads: {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=45, show_spinner=False)
def _fetch_loads_cached(tenant_id: str) -> pd.DataFrame:
    """Cached loads (45s) — tenant-scoped."""
    from lp_helpers.repositories.loads import list_loads

    with closing(get_connection()) as conn:
        return list_loads(conn, tenant_id=tenant_id)


def fetch_loads() -> pd.DataFrame:
    """Loads for current tenant (cache key = tenant_id)."""
    try:
        from lp_helpers.tenancy import current_tenant_id

        return _fetch_loads_cached(current_tenant_id())
    except Exception as exc:
        log.exception("fetch_loads failed")
        st.error(f"Could not load loads: {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def fetch_lane_rates() -> pd.DataFrame:
    """Cached lane rates (2 min)."""
    try:
        with closing(get_connection()) as conn:
            return pd.read_sql_query(
                "SELECT * FROM lane_rates ORDER BY origin, destination, commodity",
                conn,
            )
    except Exception as exc:
        log.exception("fetch_lane_rates failed")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_call_logs() -> pd.DataFrame:
    """Cached recent call logs (60s)."""
    try:
        with closing(get_connection()) as conn:
            return pd.read_sql_query(
                """
                SELECT c.*, l.company
                FROM call_logs c
                LEFT JOIN leads l ON c.lead_id = l.id
                ORDER BY c.logged_at DESC
                LIMIT 50
                """,
                conn,
            )
    except Exception as exc:
        log.exception("fetch_call_logs failed")
        return pd.DataFrame()


def clear_data_caches() -> None:
    """Invalidate cached tables after inserts/updates so UI stays fresh."""
    try:
        _fetch_leads_cached.clear()
        _fetch_loads_cached.clear()
        fetch_call_logs.clear()
        fetch_lane_rates.clear()
    except Exception:
        pass


# Friendly aliases (docs / future call sites)
fetch_leads_cached = fetch_leads
fetch_loads_cached = fetch_loads


def run_platform_health_check() -> None:
    """In-app diagnostics: DB, theme, nav, driver module, caches."""
    st.subheader("Platform Health Check")
    st.caption("Quick diagnostics for Dispatch stability and data access.")

    checks: list[tuple[str, str]] = []

    # 1) Database
    try:
        with closing(get_connection()) as conn:
            conn.execute("SELECT 1")
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        required = {"leads", "loads"}
        missing = required - tables
        if missing:
            checks.append(("Database Connection", f"WARN missing tables: {', '.join(sorted(missing))}"))
        else:
            checks.append(("Database Connection", "OK"))
    except Exception as exc:
        checks.append(("Database Connection", f"FAIL {exc}"))

    # 2) Theme
    if "night_mode" in st.session_state:
        mode = "Night" if st.session_state.night_mode else "Day"
        checks.append(("Theme System", f"OK ({mode} mode)"))
    else:
        checks.append(("Theme System", "WARN not initialized"))

    # 3) Navigation
    nav_ok = callable(globals().get("navigate_to_tab")) and callable(
        globals().get("render_main_nav")
    )
    checks.append(("Navigation Function", "OK" if nav_ok else "FAIL Missing"))

    # 4) Driver module
    try:
        from lp_helpers.driver_mobile import render_driver_app

        checks.append(
            ("Driver Module", "OK" if callable(render_driver_app) else "FAIL not callable")
        )
    except Exception as exc:
        checks.append(("Driver Module", f"FAIL {exc}"))

    # 5) Platform theme helper
    try:
        from lp_helpers.ui_theme import apply_platform_theme as _theme

        checks.append(("Accessibility Theme", "OK" if callable(_theme) else "FAIL"))
    except Exception as exc:
        checks.append(("Accessibility Theme", f"FAIL {exc}"))

    # 6) Cached fetchers
    try:
        _ = fetch_leads()
        _ = fetch_loads()
        checks.append(("Cached Data Fetch", "OK (leads + loads)"))
    except Exception as exc:
        checks.append(("Cached Data Fetch", f"FAIL {exc}"))

    # 7) Multi-tenant foundation
    try:
        from lp_helpers.fleet_context import get_tenant_context
        from lp_helpers.tenancy import DEFAULT_TENANT_ID

        ctx = get_tenant_context()
        checks.append(
            (
                "Tenant Context",
                f"OK ({ctx.tenant_id})" if ctx.tenant_id == DEFAULT_TENANT_ID or ctx.tenant_id else f"OK ({ctx.tenant_id})",
            )
        )
    except Exception as exc:
        checks.append(("Tenant Context", f"FAIL {exc}"))

    # 8) Telematics port
    try:
        from lp_helpers.integrations.telematics_port import get_telematics_port

        port = get_telematics_port(get_secret=get_secret)
        st_status = port.connection_status()
        checks.append(
            ("Telematics Port", f"OK ({st_status.provider}/{st_status.mode})")
        )
    except Exception as exc:
        checks.append(("Telematics Port", f"FAIL {exc}"))

    for name, status in checks:
        if status.startswith("OK"):
            st.success(f"**{name}:** {status}")
        elif status.startswith("WARN"):
            st.warning(f"**{name}:** {status}")
        else:
            st.error(f"**{name}:** {status}")

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Force Refresh All Cached Data", use_container_width=True, key="health_clear_cache"):
            clear_data_caches()
            try:
                st.cache_data.clear()
            except Exception:
                pass
            st.success("Cache cleared. Refreshing...")
            st.rerun()
    with col_b:
        if st.button("Open Driver View (Beta)", use_container_width=True, key="health_open_driver"):
            st.session_state.view_mode = "driver"
            st.rerun()


def compute_dashboard_metrics(
    leads_df: pd.DataFrame, loads_df: pd.DataFrame
) -> dict[str, float | int]:
    hot_leads = 0
    if not leads_df.empty:
        hot_leads = int(leads_df["status"].astype(str).isin(["Hot", "Active", "Negotiating"]).sum())

    if loads_df.empty:
        return {
            "hot_leads": hot_leads,
            "loads_logged": 0,
            "pipeline_revenue": 0.0,
            "avg_rate_per_ton": 0.0,
            "loaded_share": 0.0,
            "deadhead_miles": 0.0,
            "in_transit": 0,
        }

    pipeline_revenue = float(loads_df["total_revenue"].fillna(0).sum())
    total_tons = float(loads_df["weight_tons"].fillna(0).sum())
    if total_tons > 0:
        avg_rate_per_ton = pipeline_revenue / total_tons
    else:
        rates = loads_df["rate_per_ton"].dropna()
        avg_rate_per_ton = float(rates.mean()) if not rates.empty else 0.0

    miles_col = loads_df["miles"] if "miles" in loads_df.columns else pd.Series(0, index=loads_df.index)
    if "loaded_miles" in loads_df.columns:
        loaded = float(loads_df["loaded_miles"].fillna(miles_col).fillna(0).sum())
    else:
        loaded = float(miles_col.sum())
    total_miles = float(miles_col.sum()) if "miles" in loads_df.columns else loaded
    if "deadhead_miles" in loads_df.columns:
        deadhead = float(loads_df["deadhead_miles"].fillna(0).sum())
    else:
        deadhead = 0.0
    if deadhead <= 0 and total_miles > 0:
        deadhead = max(0.0, total_miles - loaded)
    loaded_share = (loaded / total_miles) if total_miles > 0 else 0.0
    in_transit = int(
        loads_df["status"].astype(str).isin(["Dispatched", "In Transit"]).sum()
    )

    return {
        "hot_leads": hot_leads,
        "loads_logged": len(loads_df),
        "pipeline_revenue": pipeline_revenue,
        "avg_rate_per_ton": avg_rate_per_ton,
        "loaded_share": loaded_share,
        "deadhead_miles": deadhead,
        "in_transit": in_transit,
    }


def calculate_rate(
    weight_tons: float,
    miles: float,
    loaded_miles: float | None = None,
    commodity: str = "",
) -> tuple[float, float]:
    base = PRIMARY_LANE["baseline_rate_per_ton"]
    lm = loaded_miles if loaded_miles and loaded_miles > 0 else miles
    loaded_share = lm / miles if miles > 0 else 1.0

    if loaded_share >= 0.95:
        multiplier = 1.05
    elif loaded_share >= 0.85:
        multiplier = 1.02
    elif loaded_share < 0.70:
        multiplier = 0.95
    else:
        multiplier = 1.0

    commodity_lower = commodity.lower()
    if any(c in commodity_lower for c in ("feldspar", "mica", "spar", "clay", "quartz")):
        multiplier *= 1.02
    elif "fertilizer" in commodity_lower:
        multiplier *= 1.03
    elif "lime" in commodity_lower:
        multiplier *= 1.01

    rate = round(base * multiplier, 2)
    revenue = round(rate * weight_tons, 2)
    return rate, revenue


def generate_bol_number() -> str:
    return f"LP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def generate_bol_pdf(load: dict) -> bytes:
    try:
        from lp_helpers.bol_export import generate_branded_bol_pdf

        return generate_branded_bol_pdf(load, app_version=APP_VERSION)
    except ImportError:
        pass
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Lawson Freight Platform", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Bill of Lading - Spruce Pine NC - 39ft frameless end-dump", ln=True)
    pdf.ln(4)

    rows = [
        ("BOL #", str(load.get("bol_number", "-"))),
        ("Date", str(load.get("pickup_date") or load.get("load_date") or date.today())),
        ("Shipper", str(load.get("shipper", "-"))),
        ("Commodity", str(load.get("commodity", "-"))),
        ("Origin", str(load.get("origin", TARGET_LANE_ORIGIN))),
        ("Destination", str(load.get("destination", "-"))),
        ("Weight (tons)", str(load.get("weight_tons", "-"))),
        ("Miles", str(load.get("miles", "-"))),
        ("Loaded Miles", str(load.get("loaded_miles", "-"))),
        ("Rate/Ton", f"${float(load.get('rate_per_ton', 0)):.2f}"),
        ("Total Revenue", f"${float(load.get('total_revenue', 0)):,.2f}"),
        ("Status", str(load.get("status", "Logged"))),
    ]
    pdf.set_font("Helvetica", "", 10)
    for label, value in rows:
        pdf.cell(45, 7, label, border=1)
        pdf.cell(0, 7, value, border=1, ln=True)

    notes = load.get("notes")
    if notes:
        pdf.ln(4)
        pdf.multi_cell(0, 6, f"Notes: {notes}")

    pdf.ln(8)
    pdf.cell(0, 7, "Shipper Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Driver Signature: _________________________  Date: __________", ln=True)
    pdf.ln(6)
    pdf.cell(0, 7, "Receiver Signature: _______________________  Date: __________", ln=True)

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)


def bol_pdf_filename(load: dict) -> str:
    bol = str(load.get("bol_number", "DRAFT")).replace("/", "-").replace(" ", "_")
    pickup = str(load.get("pickup_date") or load.get("load_date") or date.today())[:10]
    return f"Lawson_BOL_{bol}_{pickup.replace('-', '')}.pdf"


def score_trailer_fit(commodity: str, weight: float, notes: str = "") -> dict[str, str | list[str]]:
    """Rule-based trailer fit for 39ft / 24-ton frameless end-dump."""
    reasons: list[str] = []
    commodity_lower = commodity.lower().strip()
    notes_lower = notes.lower()

    if weight > TRAILER_MAX_TONS:
        return {
            "level": "Low",
            "color": "red",
            "reasons": [f"Weight {weight:.1f}t exceeds {TRAILER_MAX_TONS}t rated capacity."],
        }

    if any(kw in commodity_lower or kw in notes_lower for kw in LOW_FIT_KEYWORDS):
        reasons.append("Commodity or notes flag compatibility concerns for a mineral end-dump.")
        if any(kw in commodity_lower or kw in notes_lower for kw in WASHOUT_KEYWORDS):
            reasons.append("Washout likely required before next fine/mineral load.")
        return {"level": "Low", "color": "red", "reasons": reasons}

    if commodity_lower == "other" or commodity_lower not in HIGH_FIT_COMMODITIES | MEDIUM_FIT_COMMODITIES:
        if commodity_lower == "other":
            reasons.append("Unspecified commodity — confirm tarp, lining, and washout rules.")
        else:
            reasons.append(f"{commodity} not on core approved list — verify before booking.")
        return {"level": "Medium", "color": "orange", "reasons": reasons}

    if commodity_lower in MEDIUM_FIT_COMMODITIES or "fertilizer" in commodity_lower:
        reasons.append("Acceptable with lined end-dump — confirm tarp and residue plan.")
        return {"level": "Medium", "color": "orange", "reasons": reasons}

    reasons.append("Core Spruce Pine mineral/aggregate fit for 39ft frameless end-dump.")
    if weight >= TRAILER_MAX_TONS * 0.9:
        reasons.append(f"Near capacity at {weight:.1f}t — confirm scale ticket.")
    return {"level": "High", "color": "green", "reasons": reasons}


def resolve_rate_and_revenue(
    weight: float,
    rate_per_ton: float | None,
    total_revenue: float | None,
    pricing_mode: str,
) -> tuple[float, float]:
    if weight <= 0:
        return 0.0, 0.0
    if pricing_mode == "Total revenue" and total_revenue and total_revenue > 0:
        return round(total_revenue / weight, 2), round(total_revenue, 2)
    if rate_per_ton and rate_per_ton > 0:
        return round(rate_per_ton, 2), round(rate_per_ton * weight, 2)
    if total_revenue and total_revenue > 0:
        return round(total_revenue / weight, 2), round(total_revenue, 2)
    return 0.0, 0.0


def commodity_rate_multiplier(commodity: str) -> float:
    commodity_lower = commodity.lower()
    if any(c in commodity_lower for c in ("feldspar", "mica", "spar", "clay", "quartz")):
        return 1.02
    if "fertilizer" in commodity_lower:
        return 1.03
    if "lime" in commodity_lower:
        return 1.01
    if commodity_lower == "other":
        return 1.0
    return 1.0


def compute_quote_metrics(
    weight: float,
    miles: float,
    deadhead_miles: float,
    rate_per_ton: float,
    commodity: str,
) -> dict[str, float | str]:
    revenue = round(rate_per_ton * weight, 2)
    rpm = revenue / miles if miles > 0 else 0.0
    deadhead_cost = round(deadhead_miles * (FUEL_COST_PER_MILE + OPS_COST_PER_MILE), 2)
    net_after_deadhead = round(revenue - deadhead_cost, 2)
    margin_pct = (net_after_deadhead / revenue) if revenue > 0 else 0.0

    base = PRIMARY_LANE["baseline_rate_per_ton"] * commodity_rate_multiplier(commodity)
    rate_low = round(base * 0.92, 2)
    rate_mid = round(base, 2)
    rate_high = round(base * 1.08, 2)

    return {
        "revenue": revenue,
        "rpm": rpm,
        "deadhead_cost": deadhead_cost,
        "net_after_deadhead": net_after_deadhead,
        "margin_pct": margin_pct,
        "rate_low": rate_low,
        "rate_mid": rate_mid,
        "rate_high": rate_high,
    }


def apply_load_prefill(prefill: dict) -> None:
    """Push Rate Calculator values into Load Logger widget session state."""
    if "pickup_date" in prefill:
        st.session_state.load_pickup_date = prefill["pickup_date"]
    if prefill.get("status") in LOAD_STATUS_OPTIONS:
        st.session_state.load_status = prefill["status"]
    if prefill.get("shipper_pick"):
        st.session_state.load_shipper_pick = prefill["shipper_pick"]
    if "shipper" in prefill:
        st.session_state.load_shipper_text = prefill["shipper"]
    if prefill.get("commodity") in APPROVED_COMMODITIES:
        st.session_state.load_commodity = prefill["commodity"]
    elif prefill.get("commodity"):
        st.session_state.load_commodity = "Other"
        st.session_state.load_commodity_other = prefill["commodity"]
    if "weight" in prefill:
        st.session_state.load_weight = float(prefill["weight"])
    if prefill.get("pricing_mode"):
        st.session_state.load_pricing_mode = prefill["pricing_mode"]
    if "rate_per_ton" in prefill:
        st.session_state.load_rate_per_ton = float(prefill["rate_per_ton"])
    if "total_revenue" in prefill:
        st.session_state.load_total_revenue = float(prefill["total_revenue"])
    if "destination" in prefill:
        st.session_state.load_destination = prefill["destination"]
    if "notes" in prefill:
        st.session_state.load_notes = prefill["notes"]
    if "miles" in prefill:
        st.session_state["_load_prefill_miles"] = float(prefill["miles"])
    if "loaded_miles" in prefill:
        st.session_state["_load_prefill_loaded_miles"] = float(prefill["loaded_miles"])


def prefill_load_logger(**kwargs) -> None:
    st.session_state.load_prefill = kwargs
    navigate_to_tab("Logger")


def match_lane_rates(
    origin: str, destination: str, commodity: str, lane_rates_df: pd.DataFrame
) -> pd.DataFrame:
    if lane_rates_df.empty:
        return lane_rates_df

    matches = lane_rates_df.copy()
    matches["match_score"] = 0
    for idx, row in matches.iterrows():
        score = 0
        if str(row.get("origin", "")).lower() in origin.lower() or origin.lower() in str(row.get("origin", "")).lower():
            score += 2
        if str(row.get("destination", "")).lower() in destination.lower() or destination.lower() in str(row.get("destination", "")).lower():
            score += 2
        if str(row.get("commodity", "")).lower() == commodity.lower():
            score += 3
        elif commodity.lower() in str(row.get("commodity", "")).lower():
            score += 1
        matches.at[idx, "match_score"] = score

    return matches[matches["match_score"] > 0].sort_values("match_score", ascending=False)


def navigate_to_tab(tab_name: str) -> None:
    """Navigate using single source of truth: st.session_state['active_tab'].

    Never mutates Streamlit widget keys (avoids StreamlitAPIException).
    Preserves filters/forms: only active_tab + optional nav_hint change.
    """
    if tab_name == "Rates":
        st.session_state.open_rates_expander = True
        tab_name = "Dashboard"
    if tab_name not in TAB_KEYS:
        try:
            st.warning(f"Unknown tab: {tab_name}")
        except Exception:
            pass
        return
    st.session_state["active_tab"] = tab_name
    label = TAB_LABELS[TAB_KEYS.index(tab_name)]
    st.session_state.nav_hint = f"Opened **{label}**"
    st.rerun()


def render_main_nav() -> str:
    """Button-based nav — active_tab is the only source of truth (Streamlit-safe).

    Research note: Streamlit forbids writing to a widget's session key after that
    widget is instantiated. Radio/select with key='main_nav_radio' caused jumps
    and StreamlitAPIException when Quick Actions set that key mid-run.
    Buttons only write active_tab, matching Samsara/Motive-style explicit nav.
    """
    if "active_tab" not in st.session_state or st.session_state.active_tab not in TAB_KEYS:
        st.session_state.active_tab = "Dashboard"

    active = st.session_state.active_tab
    cols = st.columns(len(TAB_KEYS))
    for i, key in enumerate(TAB_KEYS):
        label = TAB_LABELS[i]
        is_active = key == active
        with cols[i]:
            if st.button(
                label,
                key=f"nav_btn_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                if key != active:
                    st.session_state.active_tab = key
                    st.rerun()
    return st.session_state.active_tab


def _persist_owner_role() -> None:
    role = st.session_state.get("lawson_owner_role", DEFAULT_OWNER)
    if role in OWNERS:
        set_active_owner(role)


def render_lawson_sidebar_extras() -> None:
    """Owner role selector (kept for compatibility with older call sites)."""
    try:
        current_owner = get_active_owner()
        owner_index = list(OWNERS).index(current_owner) if current_owner in OWNERS else 0
        selected_owner = st.selectbox(
            "Operating as",
            list(OWNERS),
            index=owner_index,
            key="owner_selector",
        )
        if selected_owner != current_owner:
            set_active_owner(selected_owner)
            st.rerun()
    except Exception as exc:
        st.error(f"Owner selector error: {exc}")
        st.caption(f"Defaulting to {DEFAULT_OWNER}")
        st.session_state["owner_role"] = DEFAULT_OWNER


def render_sidebar() -> None:
    """Combined sidebar with safe owner selector, theme toggle, and Driver View."""
    with st.sidebar:
        st.markdown(f"### {CARRIER_NAME}")
        st.caption(
            f"{TARGET_LANE_ORIGIN} -> {TARGET_LANE_DESTINATION} | {TRAILER_DESC}"
        )

        # === Safe Owner Selector with Error Handling ===
        try:
            current_owner = get_active_owner()
            owner_index = list(OWNERS).index(current_owner) if current_owner in OWNERS else 0

            selected_owner = st.selectbox(
                "Operating as",
                list(OWNERS),
                index=owner_index,
                key="owner_selector",
            )

            if selected_owner != current_owner:
                set_active_owner(selected_owner)
                st.rerun()

        except Exception as e:
            st.error(f"Owner selector error: {e}")
            st.session_state["owner_role"] = DEFAULT_OWNER

        st.divider()

        # Day / Night Toggle
        try:
            from lp_helpers.ui_components import render_day_night_toggle as _day_night
        except ImportError:
            _day_night = render_day_night_toggle
        _day_night()

        st.divider()

        # Safe Driver View Button
        if st.button("Driver View (Beta)", use_container_width=True, key="driver_view_btn"):
            st.session_state.view_mode = "driver"
            st.rerun()

        if st.button("Platform Health Check", use_container_width=True, key="sidebar_health_btn"):
            # Use active_tab only — never set main_nav_radio mid-run
            st.session_state.active_tab = "Alerts"
            st.session_state.nav_hint = "Opened **Alerts** — expand Platform Health Check"
            st.rerun()

        st.caption(f"{APP_VERSION} · {get_active_owner()} · Board · GPS · Alerts")


def render_target_lane_banner() -> None:
    lane_col1, lane_col2, lane_col3 = st.columns([2, 1, 2])
    with lane_col1:
        st.markdown(
            f"<div style='text-align:right;font-size:1.1rem;font-weight:700;'>"
            f"📍 {TARGET_LANE_ORIGIN}</div>",
            unsafe_allow_html=True,
        )
    with lane_col2:
        st.markdown(
            "<div style='text-align:center;font-size:1.4rem;font-weight:800;"
            "color:var(--lf-orange);padding:0.25rem 0;'>➜ TARGET LANE ➜</div>",
            unsafe_allow_html=True,
        )
    with lane_col3:
        st.markdown(
            f"<div style='text-align:left;font-size:1.1rem;font-weight:700;'>"
            f"🏁 {TARGET_LANE_DESTINATION}</div>",
            unsafe_allow_html=True,
        )


def _render_deadhead_return_panel(loads_df: pd.DataFrame) -> None:
    """Primary Dashboard panel: I'm empty now → score returns with $ benefit."""
    st.markdown("---")
    render_section_header("I'm empty — find a return home", icon="🔄")

    try:
        from lp_helpers.deadhead import (
            DEFAULT_DELIVERY_ZONE,
            DEFAULT_LANE_BASELINE_PER_TON,
            estimate_empty_home_miles,
            estimate_return_benefit,
            last_delivery_location,
            opportunities_as_candidates,
            rank_return_candidates,
            score_return_load,
        )
    except Exception as exc:
        st.warning(f"Deadhead helper unavailable: {exc}")
        return

    detected = last_delivery_location(loads_df) or DEFAULT_DELIVERY_ZONE
    if "dh_empty_at" not in st.session_state:
        st.session_state.dh_empty_at = detected

    # --- I'm empty now strip ---
    strip = st.container()
    with strip:
        s1, s2, s3 = st.columns([2, 1.2, 1])
        with s1:
            empty_at = st.text_input(
                "I'm empty near",
                key="dh_empty_at",
                help="Usually last delivery (Central GA). Change if you're elsewhere.",
            )
        with s2:
            if st.button("Use last delivery", use_container_width=True, key="dh_use_last"):
                st.session_state.dh_empty_at = detected
                st.rerun()
        with s3:
            if st.button("Central GA", use_container_width=True, key="dh_use_ga"):
                st.session_state.dh_empty_at = DEFAULT_DELIVERY_ZONE
                st.rerun()

    empty_at = st.session_state.get("dh_empty_at") or detected
    empty_home = estimate_empty_home_miles(empty_at, TARGET_LANE_ORIGIN)
    pure_empty_fuel = empty_home * FUEL_COST_PER_MILE

    h1, h2, h3 = st.columns(3)
    h1.metric("Empty near", empty_at[:28] + ("…" if len(empty_at) > 28 else ""))
    h2.metric("Empty home (est.)", f"{empty_home:.0f} mi")
    h3.metric("Fuel if pure empty", f"${pure_empty_fuel:,.0f}")
    st.caption(
        f"Home corridor: **{TARGET_LANE_ORIGIN}** · Baseline bulk ~**${DEFAULT_LANE_BASELINE_PER_TON:g}/ton**. "
        "Estimates are corridor heuristics — not GPS routes."
    )

    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("##### Score a broker offer")
        r1, r2 = st.columns(2)
        ret_origin = r1.text_input(
            "Pickup",
            value="Central Georgia",
            key="dh_origin",
        )
        ret_dest = r2.text_input(
            "Drop (toward home)",
            value="Spruce Pine / Asheville, NC",
            key="dh_dest",
        )
        r3, r4, r5 = st.columns(3)
        ret_commodity = r3.selectbox(
            "Commodity",
            ["Feldspar", "Aggregate", "Sand", "Gravel", "Clay", "Lime", "Other"],
            key="dh_commodity",
        )
        ret_rate = r4.text_input("Rate ($/ton)", value="45", key="dh_rate")
        ret_tons = r5.number_input("Tons", min_value=1.0, max_value=30.0, value=24.0, step=0.5, key="dh_tons")

        scored = score_return_load(
            origin=ret_origin,
            destination=ret_dest,
            commodity=ret_commodity,
            rate_hint=ret_rate,
            current_location=empty_at,
            home=TARGET_LANE_ORIGIN,
        )
        benefit = estimate_return_benefit(
            scored,
            origin=ret_origin,
            destination=ret_dest,
            current_location=empty_at,
            home=TARGET_LANE_ORIGIN,
            weight_tons=float(ret_tons),
            fuel_cost_per_mile=FUEL_COST_PER_MILE,
        )

        # Result card
        if scored.grade in ("A", "B"):
            st.success(f"**{scored.grade} · {scored.score}/100** — {scored.label}")
        elif scored.grade == "C":
            st.warning(f"**{scored.grade} · {scored.score}/100** — {scored.label}")
        else:
            st.error(f"**{scored.grade} · {scored.score}/100** — {scored.label}")

        b1, b2, b3 = st.columns(3)
        b1.metric("Est. revenue", f"${benefit['est_revenue']:,.0f}")
        b2.metric("Fuel to shipper", f"${benefit['extra_empty_fuel']:,.0f}")
        b3.metric(
            "Net vs pure empty",
            f"${benefit['net_benefit_vs_empty']:,.0f}",
            help="Rough: return revenue minus fuel burned empty to that pickup",
        )
        st.caption(benefit["blurb"])

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Near me", f"{scored.proximity_pts}/25")
        p2.metric("Homebound", f"{scored.direction_pts}/35")
        p3.metric("Dump fit", f"{scored.commodity_pts}/20")
        p4.metric("Rate", f"{scored.rate_pts}/20")

        with st.expander("Why this score", expanded=False):
            for reason in scored.reasons:
                st.markdown(f"- {reason}")

        cta1, cta2 = st.columns(2)
        with cta1:
            if st.button("Log as potential load", type="primary", use_container_width=True, key="dh_to_logger"):
                prefill_load_logger(
                    shipper="",
                    commodity=ret_commodity if ret_commodity != "Other" else "Aggregate",
                    origin=ret_origin,
                    destination=ret_dest,
                    weight=float(ret_tons),
                    rate_per_ton=float(str(ret_rate).replace("/ton", "").strip() or 0) or None,
                    status="Potential",
                    notes=(
                        f"Return home · grade {scored.grade} ({scored.score}) · "
                        f"est net ${benefit['net_benefit_vs_empty']:,.0f} vs empty"
                    ),
                )
        with cta2:
            if st.button("Open Board tab", use_container_width=True, key="dh_to_board"):
                navigate_to_tab("Board")

    with right:
        st.markdown("##### Best returns on your board")
        try:
            with closing(get_connection()) as conn:
                opp_df = pd.read_sql_query(
                    "SELECT * FROM opportunities ORDER BY created_at DESC LIMIT 40",
                    conn,
                )
        except Exception:
            opp_df = pd.DataFrame()

        if opp_df.empty:
            st.info("No board rows yet — score a call-in on the left, or add offers on **Board**.")
        else:
            ranked = rank_return_candidates(
                opportunities_as_candidates(opp_df),
                home=TARGET_LANE_ORIGIN,
                current_location=empty_at,
            )[:5]
            for i, (cand, sc) in enumerate(ranked):
                ben = estimate_return_benefit(
                    sc,
                    origin=str(cand.get("origin") or ""),
                    destination=str(cand.get("destination") or cand.get("lane") or ""),
                    current_location=empty_at,
                    home=TARGET_LANE_ORIGIN,
                    fuel_cost_per_mile=FUEL_COST_PER_MILE,
                )
                lane = cand.get("lane") or f"{cand.get('origin')} → {cand.get('destination')}"
                icon = "🟢" if sc.grade in ("A", "B") else ("🟡" if sc.grade == "C" else "🔴")
                st.markdown(
                    f"{icon} **{sc.grade} {sc.score}** · {lane}  \n"
                    f"{cand.get('commodity') or '—'} · {cand.get('rate') or 'n/a'} · "
                    f"**~${ben['net_benefit_vs_empty']:,.0f}** vs empty"
                )
                st.caption(sc.label)
                if st.button("Use this", key=f"dh_use_{i}", use_container_width=True):
                    prefill_load_logger(
                        shipper=str(cand.get("contact") or ""),
                        commodity=str(cand.get("commodity") or "Aggregate"),
                        origin=str(cand.get("origin") or empty_at),
                        destination=str(cand.get("destination") or ""),
                        status="Potential",
                        notes=f"Board return · {sc.grade} {sc.score} · {lane}",
                    )
                st.divider()

    with st.expander("Limits of this v1 helper", expanded=False):
        st.markdown(
            """
**What it does well:** ranks *near me* + *toward home* + *end-dump fit* + *rate vs ~$48/ton* in plain language.

**What it does *not* do yet:** real road miles, plant wait time, live load boards, or multi-stop optimization.

**v2 worth building:** GPS empty-mile calc, history of what *you* paid on returns, optional DAT/Truckstop feed.
            """
        )


def render_dashboard_tab() -> None:
    st.subheader("Dashboard")

    leads_df = fetch_leads()
    loads_df = fetch_loads()
    metrics = compute_dashboard_metrics(leads_df, loads_df)

    render_target_lane_banner()

    st.info(f"**{CARRIER_NAME} Mission:** {MISSION_BLURB}")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    loaded_pct = metrics["loaded_share"]
    loaded_delta = (
        f"{(loaded_pct - LOADED_MILE_TARGET):.0%} vs target"
        if loaded_pct > 0
        else f"Target {LOADED_MILE_TARGET:.0%}"
    )
    kpi1.metric(
        "Loaded Mile Share",
        f"{loaded_pct:.0%}",
        delta=loaded_delta,
        delta_color="normal" if loaded_pct >= LOADED_MILE_TARGET else "inverse",
        help=f"Target ≥ {LOADED_MILE_TARGET:.0%} loaded miles — empty miles kill margin",
    )
    kpi2.metric("Pipeline Revenue", f"${metrics['pipeline_revenue']:,.0f}")
    kpi3.metric(
        "Deadhead Miles",
        f"{metrics['deadhead_miles']:,.0f}",
        help="Empty miles on logged loads — minimize for margin",
    )
    kpi4.metric("Avg Rate / Ton", f"${metrics['avg_rate_per_ton']:.2f}")

    kpi5, kpi6, kpi7, kpi8 = st.columns(4)
    kpi5.metric("Hot / Active Leads", metrics["hot_leads"])
    kpi6.metric("Loads Logged", metrics["loads_logged"])
    kpi7.metric("In Transit / Dispatched", metrics["in_transit"])
    kpi8.metric("Primary Receiver", PRIMARY_RECEIVER[:16])

    with st.expander("🚨 Emergency Dispatch", expanded=False):
        _render_emergency_controls(key_prefix="dash_em", compact=True)

    # --- First-class deadhead panel (not buried in expander) ---
    _render_deadhead_return_panel(loads_df)

    st.markdown("#### Quick Actions")
    action1, action2, action3, action4 = st.columns(4)
    if action1.button("Log New Call / Update Lead", use_container_width=True, key="qa_leads"):
        navigate_to_tab("Leads")
    if action2.button("Log Potential Load", use_container_width=True, key="qa_logger"):
        navigate_to_tab("Logger")
    if action3.button("Open Rate Calculator", use_container_width=True, key="qa_rates"):
        st.session_state.open_rates_expander = True
        navigate_to_tab("Dashboard")
    if action4.button("Generate BOL", use_container_width=True, key="qa_bol"):
        navigate_to_tab("BOL")

    st.divider()
    render_section_header("Analytics", icon="📊")

    if not loads_df.empty and px is not None:
        try:
            from lp_helpers.analytics_dashboard import (
                build_deadhead_chart,
                build_rate_per_mile_chart,
                build_revenue_chart,
                build_status_pie,
            )

            chart_left, chart_right = st.columns(2)
            with chart_left:
                rev_fig = build_revenue_chart(loads_df)
                if rev_fig:
                    st.plotly_chart(rev_fig, use_container_width=True)
                elif not loads_df.empty:
                    shipper_rev = (
                        loads_df.groupby("shipper", as_index=False)["total_revenue"]
                        .sum()
                        .sort_values("total_revenue", ascending=False)
                    )
                    fig = px.bar(
                        shipper_rev,
                        x="shipper",
                        y="total_revenue",
                        color="shipper",
                        title="Revenue by Shipper",
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
            with chart_right:
                status_fig = build_status_pie(loads_df)
                if status_fig:
                    st.plotly_chart(status_fig, use_container_width=True)
            chart_left2, chart_right2 = st.columns(2)
            with chart_left2:
                rate_fig = build_rate_per_mile_chart(loads_df)
                if rate_fig:
                    st.plotly_chart(rate_fig, use_container_width=True)
            with chart_right2:
                dh_fig = build_deadhead_chart(loads_df)
                if dh_fig:
                    st.plotly_chart(dh_fig, use_container_width=True)
        except ImportError:
            if px is not None and "total_revenue" in loads_df.columns:
                fig = px.bar(
                    loads_df,
                    x="shipper",
                    y="total_revenue",
                    color="commodity",
                    title="Pipeline Revenue by Shipper",
                )
                st.plotly_chart(fig, use_container_width=True)
    elif loads_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state(
            "📋",
            "No loads logged yet",
            "Log your first load in the Logger tab to unlock revenue and deadhead analytics.",
        )
    else:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state(
            "📊",
            "Plotly not installed",
            "Install plotly for interactive dashboard charts: pip install plotly",
        )

    st.divider()
    render_section_header("Recent Activity", icon="🕒")

    activity_left, activity_right = st.columns(2)

    with activity_left:
        st.markdown("**Last 5 Loads**")
        if loads_df.empty:
            from lp_helpers.ui_components import render_empty_state

            render_empty_state("📦", "No loads logged yet.")
        else:
            load_cols = [
                c
                for c in [
                    "load_date",
                    "shipper",
                    "commodity",
                    "weight_tons",
                    "total_revenue",
                    "status",
                ]
                if c in loads_df.columns
            ]
            st.dataframe(
                loads_df[load_cols].head(5),
                use_container_width=True,
                hide_index=True,
            )

    with activity_right:
        st.markdown("**Last 5 Lead Notes**")
        if leads_df.empty:
            from lp_helpers.ui_components import render_empty_state

            render_empty_state("📝", "No leads in CRM.")
        else:
            notes_df = leads_df.copy()
            notes_df["notes"] = notes_df["notes"].fillna("").astype(str)
            notes_df = notes_df[notes_df["notes"].str.strip() != ""]
            if notes_df.empty:
                from lp_helpers.ui_components import render_empty_state

                render_empty_state("💬", "No lead notes recorded yet.")
            else:
                sort_col = (
                    "last_contact"
                    if "last_contact" in notes_df.columns
                    else "created_at"
                )
                notes_df = notes_df.sort_values(sort_col, ascending=False, na_position="last")
                lead_activity = notes_df[["company", "status", "notes", sort_col]].head(5)
                lead_activity = lead_activity.rename(columns={sort_col: "last_updated"})
                st.dataframe(
                    lead_activity,
                    use_container_width=True,
                    hide_index=True,
                )

    rates_open = st.session_state.pop("open_rates_expander", False)
    with st.expander("💰 Rate Calculator", expanded=rates_open):
        render_rate_calculator_tab(embedded=True)


def render_leads_crm_tab() -> None:
    st.subheader("Leads")
    st.caption("Log calls, update status, and track Spruce Pine shipper outreach.")

    leads_df = fetch_leads()
    if leads_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state(
            "📞",
            "No leads found",
            "Hot leads will seed automatically on next refresh, or add them manually.",
        )
        return

    fc1, fc2 = st.columns([1, 2])
    status_filter = fc1.selectbox(
        "Filter by status",
        ["All"] + LEAD_STATUS_OPTIONS,
        index=(["All"] + LEAD_STATUS_OPTIONS).index(
            st.session_state.get("filter_leads_status", "All")
        )
        if st.session_state.get("filter_leads_status", "All") in ["All"] + LEAD_STATUS_OPTIONS
        else 0,
        key="leads_status_filter_ui",
    )
    search = fc2.text_input(
        "Search company / notes",
        value=st.session_state.get("filter_leads_search", ""),
        key="leads_search_ui",
    )
    if status_filter != st.session_state.get("filter_leads_status"):
        save_filter("filter_leads_status", status_filter)
    if search != st.session_state.get("filter_leads_search"):
        save_filter("filter_leads_search", search)

    filtered = leads_df.copy()
    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]
    if search.strip():
        q = search.strip().lower()
        mask = (
            filtered["company"].astype(str).str.lower().str.contains(q, na=False)
            | filtered.get("notes", pd.Series(dtype=str)).astype(str).str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask]

    render_section_header("All Leads", icon="👥")
    display_df = filtered[
        [c for c in ["company", "phone", "commodity_focus", "status", "last_contact", "notes"] if c in filtered.columns]
    ]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()
    render_section_header("Log New Call / Update Lead", icon="📞")

    lead_options = {
        f"{row['company']} (ID {row['id']})": int(row["id"])
        for _, row in leads_df.iterrows()
    }
    selected_label = st.selectbox("Select lead", list(lead_options.keys()))
    lead_id = lead_options[selected_label]
    lead_row = leads_df[leads_df["id"] == lead_id].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        new_status = st.selectbox(
            "Status",
            LEAD_STATUS_OPTIONS,
            index=LEAD_STATUS_OPTIONS.index(lead_row["status"])
            if lead_row["status"] in LEAD_STATUS_OPTIONS
            else 0,
        )
        call_type = st.selectbox("Call type", CALL_TYPES)
        outcome = st.selectbox("Outcome", CALL_OUTCOMES)
    with col2:
        st.markdown(f"**Phone:** {lead_row.get('phone', '—')}")
        st.markdown(f"**Commodity focus:** {lead_row.get('commodity_focus', '—')}")
        call_notes = st.text_area(
            "Call / update notes",
            value="",
            placeholder="Rate discussed, callback time, load potential…",
        )

    if st.button("Save Call & Update Lead", type="primary", use_container_width=True):
        try:
            with closing(get_connection()) as conn:
                combined_notes = lead_row.get("notes") or lead_row.get("lane_notes") or ""
                if call_notes.strip():
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    combined_notes = f"{combined_notes}\n[{timestamp}] {call_notes}".strip()
                conn.execute(
                    """
                    UPDATE leads
                    SET status = ?, lane_notes = ?, last_contact = datetime('now')
                    WHERE id = ?
                    """,
                    (new_status, combined_notes, lead_id),
                )
                conn.execute(
                    """
                    INSERT INTO call_logs (lead_id, call_type, notes, outcome)
                    VALUES (?, ?, ?, ?)
                    """,
                    (lead_id, call_type, call_notes, outcome),
                )
                conn.commit()
            clear_data_caches()
            st.success(f"Updated {lead_row['company']} — status: {new_status}")
            st.rerun()
        except sqlite3.Error as exc:
            log.exception("Save lead failed")
            st.error(f"Could not save lead update: {exc}")

    st.divider()
    render_section_header("Recent Calls", icon="🕒")
    calls_df = fetch_call_logs()
    if calls_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state("📞", "No calls logged yet.")
    else:
        call_cols = [c for c in ["logged_at", "company", "call_type", "outcome", "notes"] if c in calls_df.columns]
        st.dataframe(calls_df[call_cols].head(10), use_container_width=True, hide_index=True)


def render_load_logger_tab() -> None:
    """Fast bulk load logger — core fields first, extras optional."""
    st.subheader("Log a load")
    st.caption("Bulk / end-dump speed path — shipper · commodity · tons · $/ton · destination.")

    prefill = st.session_state.pop("load_prefill", {})
    if prefill:
        apply_load_prefill(prefill)
        st.success("Prefill loaded — confirm and save.")

    leads_df = fetch_leads()
    loads_df_recent = fetch_loads()

    # Recent shippers from loads + CRM leads
    recent_shippers: list[str] = []
    if not loads_df_recent.empty and "shipper" in loads_df_recent.columns:
        for s in loads_df_recent["shipper"].dropna().astype(str):
            if s.strip() and s.strip() not in recent_shippers:
                recent_shippers.append(s.strip())
            if len(recent_shippers) >= 6:
                break
    lead_companies = leads_df["company"].astype(str).tolist() if not leads_df.empty else []
    quick_shippers = []
    for s in recent_shippers + lead_companies:
        if s not in quick_shippers:
            quick_shippers.append(s)
    quick_shippers = quick_shippers[:8]

    quick_commodities = ["Feldspar", "Quartz", "Mica", "Aggregate", "Sand", "Clay", "Lime"]

    # --- Quick picks (1 tap) ---
    if quick_shippers:
        st.markdown("**Recent shippers**")
        scols = st.columns(min(4, len(quick_shippers)))
        for i, name in enumerate(quick_shippers[:4]):
            if scols[i].button(name[:18], key=f"qs_{i}", use_container_width=True):
                st.session_state.load_shipper_text = name
                st.rerun()
        if len(quick_shippers) > 4:
            scols2 = st.columns(min(4, len(quick_shippers) - 4))
            for i, name in enumerate(quick_shippers[4:8]):
                if scols2[i].button(name[:18], key=f"qs2_{i}", use_container_width=True):
                    st.session_state.load_shipper_text = name
                    st.rerun()

    st.markdown("**Common commodities**")
    ccols = st.columns(len(quick_commodities))
    for i, com in enumerate(quick_commodities):
        if ccols[i].button(com, key=f"qc_{i}", use_container_width=True):
            st.session_state.load_commodity = com
            st.rerun()

    st.markdown("---")
    render_section_header("Core fields", icon="⚡")

    # Defaults from session/prefill
    default_shipper = st.session_state.get(
        "load_shipper_text", prefill.get("shipper", "")
    )
    default_commodity = st.session_state.get(
        "load_commodity", prefill.get("commodity", "Feldspar")
    )
    if default_commodity not in APPROVED_COMMODITIES and default_commodity not in quick_commodities:
        if default_commodity not in APPROVED_COMMODITIES:
            # keep as select index Other
            pass

    commodity_options = list(dict.fromkeys(quick_commodities + list(APPROVED_COMMODITIES)))
    if default_commodity not in commodity_options:
        commodity_options = [default_commodity] + commodity_options

    # Row 1: shipper + destination (most typed)
    shipper = st.text_input(
        "Shipper",
        value=default_shipper,
        placeholder="Plant / broker name",
        key="load_shipper_text",
    )
    destination = st.text_input(
        "Destination",
        value=st.session_state.get(
            "load_destination", prefill.get("destination", PRIMARY_LANE["destination"])
        ),
        placeholder="Receiver / city",
        key="load_destination",
    )

    # Row 2: commodity + weight + rate (bulk core)
    c1, c2, c3 = st.columns(3)
    commodity = c1.selectbox(
        "Commodity",
        commodity_options,
        index=commodity_options.index(default_commodity)
        if default_commodity in commodity_options
        else 0,
        key="load_commodity",
    )
    weight = c2.number_input(
        "Weight (tons)",
        min_value=0.0,
        max_value=30.0,
        value=float(st.session_state.get("load_weight", prefill.get("weight", 24.0))),
        step=0.5,
        key="load_weight",
    )
    rate_input = c3.number_input(
        "Rate $/ton",
        min_value=0.0,
        value=float(
            st.session_state.get(
                "load_rate_per_ton",
                prefill.get("rate_per_ton", PRIMARY_LANE["baseline_rate_per_ton"]),
            )
        ),
        step=0.25,
        key="load_rate_per_ton",
    )

    pricing_mode = "Rate per ton"
    revenue_input = 0.0
    preview_commodity = commodity
    rate_preview, revenue_preview = resolve_rate_and_revenue(
        weight, rate_input, None, pricing_mode
    )
    fit = score_trailer_fit(preview_commodity, weight, "")
    level = fit["level"]

    # Live summary strip (no extra clicks)
    sum1, sum2, sum3, sum4 = st.columns(4)
    sum1.metric("Total $", f"${revenue_preview:,.0f}")
    sum2.metric("$/ton", f"${rate_preview:.2f}")
    sum3.metric("Fit", level)
    sum4.metric("Lane mi", f"{DEFAULT_LANE_MILES}")
    st.caption(" · ".join(fit["reasons"][:2]))

    # Optional extras collapsed — widgets still run so keys exist for save
    with st.expander("More options (date, status, miles, notes)", expanded=bool(prefill.get("notes"))):
        o1, o2 = st.columns(2)
        pickup = o1.date_input(
            "Date",
            value=prefill.get("pickup_date", date.today()),
            key="load_pickup_date",
        )
        _status_opts = ["Booked", "Potential", "Quoted", "Dispatched", "In Transit", "Delivered"]
        _def_status = prefill.get("status", "Booked")
        if _def_status not in _status_opts:
            _def_status = "Booked"
        load_status = o2.selectbox(
            "Status",
            _status_opts,
            index=_status_opts.index(_def_status),
            key="load_status_simple",
        )
        o3, o4 = st.columns(2)
        origin = o3.text_input(
            "Origin",
            value=prefill.get("origin", PRIMARY_LANE["origin"]),
            key="load_origin_opt",
        )
        miles = o4.number_input(
            "Loaded miles",
            min_value=0.0,
            value=float(st.session_state.get("_load_prefill_miles", DEFAULT_LANE_MILES)),
            step=5.0,
            key="load_miles_opt",
        )
        notes = st.text_area(
            "Notes",
            value=prefill.get("notes", ""),
            placeholder="Scale, tarp, washout, gate…",
            key="load_notes",
        )
        pricing_alt = st.selectbox(
            "Price by",
            ["Rate per ton", "Total revenue"],
            key="load_pricing_mode",
        )
        if pricing_alt == "Total revenue":
            pricing_mode = "Total revenue"
            revenue_input = st.number_input(
                "Total revenue ($)",
                min_value=0.0,
                value=float(prefill.get("total_revenue", revenue_preview or 0.0)),
                step=1.0,
                key="load_total_revenue",
            )
            rate_preview, revenue_preview = resolve_rate_and_revenue(
                weight, None, revenue_input, pricing_mode
            )
            rate_input = rate_preview

    # Sync status key used elsewhere
    st.session_state.load_status = load_status

    submitted = st.button("Save load", type="primary", use_container_width=True, key="save_load_btn")

    if submitted:
        errors = validate_load_inputs(
            shipper=shipper,
            commodity=preview_commodity,
            weight=weight,
            rate_per_ton=rate_input if pricing_mode == "Rate per ton" else 0.0,
            total_revenue=revenue_input if pricing_mode == "Total revenue" else 0.0,
            pricing_mode=pricing_mode,
        )
        if errors:
            for err in errors:
                st.error(err)
        else:
            loaded_miles = float(miles)
            deadhead = float(
                st.session_state.get("_load_prefill_deadhead", DEFAULT_DEADHEAD_MILES)
            )
            # If return load (origin not home), deadhead often smaller — keep simple
            if origin and "spruce" not in str(origin).lower():
                deadhead = min(deadhead, 80.0)
            total_miles = loaded_miles + deadhead
            bol = generate_bol_number()
            try:
                from lp_helpers.repositories.loads import insert_load
                from lp_helpers.tenancy import current_tenant_id

                with closing(get_connection()) as conn:
                    insert_load(
                        conn,
                        {
                            "bol_number": bol,
                            "shipper": shipper.strip(),
                            "commodity": preview_commodity.strip(),
                            "weight_tons": weight,
                            "miles": total_miles,
                            "loaded_miles": loaded_miles,
                            "deadhead_miles": deadhead,
                            "pickup_date": str(pickup),
                            "origin": str(origin or PRIMARY_LANE["origin"]),
                            "destination": destination,
                            "rate_per_ton": rate_preview,
                            "total_revenue": revenue_preview,
                            "notes": notes or "",
                            "status": load_status,
                        },
                        tenant_id=current_tenant_id(),
                    )
                    conn.commit()
            except sqlite3.Error as exc:
                log.exception("Save load failed")
                st.error(f"Could not save load: {exc}")
                return
            clear_data_caches()
            saved_load = {
                "bol_number": bol,
                "shipper": shipper.strip(),
                "commodity": preview_commodity.strip(),
                "weight_tons": weight,
                "destination": destination,
                "status": load_status,
                "origin": str(origin or PRIMARY_LANE["origin"]),
            }
            lead_phone = None
            if not leads_df.empty:
                match = leads_df[
                    leads_df["company"].astype(str).str.lower() == shipper.strip().lower()
                ]
                if not match.empty:
                    lead_phone = str(match.iloc[0].get("phone", ""))
            notify_dispatcher_new_load(saved_load)
            maybe_auto_notify_load(saved_load, lead_phone)
            st.success(
                f"Saved · {load_status} · BOL {bol} · ${revenue_preview:,.0f} · {level} fit"
            )
            st.rerun()

    st.divider()
    render_section_header("Recent loads", icon="📋")
    loads_df = fetch_loads()
    lf1, lf2 = st.columns([1, 2])
    load_status_filter = lf1.selectbox(
        "Filter by status",
        ["All"] + LOAD_STATUS_OPTIONS,
        index=(["All"] + LOAD_STATUS_OPTIONS).index(
            st.session_state.get("filter_loads_status", "All")
        )
        if st.session_state.get("filter_loads_status", "All") in ["All"] + LOAD_STATUS_OPTIONS
        else 0,
        key="loads_status_filter_ui",
    )
    load_search = lf2.text_input(
        "Search shipper / BOL",
        value=st.session_state.get("filter_loads_search", ""),
        key="loads_search_ui",
    )
    if load_status_filter != st.session_state.get("filter_loads_status"):
        save_filter("filter_loads_status", load_status_filter)
    if load_search != st.session_state.get("filter_loads_search"):
        save_filter("filter_loads_search", load_search)

    if loads_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state("📋", "No loads logged yet.")
    else:
        view = loads_df.copy()
        if load_status_filter != "All":
            view = view[view["status"] == load_status_filter]
        if load_search.strip():
            q = load_search.strip().lower()
            view = view[
                view["shipper"].astype(str).str.lower().str.contains(q, na=False)
                | view.get("bol_number", pd.Series(dtype=str)).astype(str).str.lower().str.contains(q, na=False)
            ]
        st.dataframe(
            view[
                [
                    c
                    for c in [
                        "load_date",
                        "shipper",
                        "commodity",
                        "weight_tons",
                        "rate_per_ton",
                        "total_revenue",
                        "status",
                        "bol_number",
                    ]
                    if c in view.columns
                ]
            ].head(15),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Lane Matcher (saved benchmarks)"):
        lane_rates_df = fetch_lane_rates()
        m1, m2, m3 = st.columns(3)
        match_origin = m1.text_input(
            "Match origin", value=PRIMARY_LANE["origin"], key="match_origin"
        )
        match_dest = m2.text_input(
            "Match destination", value=PRIMARY_LANE["destination"], key="match_dest"
        )
        match_commodity = m3.selectbox(
            "Match commodity", commodity_options, key="match_commodity"
        )
        matches = match_lane_rates(
            match_origin, match_dest, match_commodity, lane_rates_df
        )
        if lane_rates_df.empty:
            st.info("No lane rates on file yet.")
        elif matches.empty:
            st.warning("No matches for this lane/commodity.")
        else:
            st.dataframe(matches, use_container_width=True, hide_index=True)


def render_rate_calculator_tab(*, embedded: bool = False) -> None:
    if not embedded:
        st.subheader("Rates")
    st.caption("Quick quoting for calls — Spruce Pine → Central GA lane")

    lane1, lane2 = st.columns(2)
    origin = lane1.text_input("Origin", value=PRIMARY_LANE["origin"], key="quote_origin")
    destination = lane2.text_input(
        "Destination", value=PRIMARY_LANE["destination"], key="quote_destination"
    )

    q1, q2, q3 = st.columns(3)
    commodity = q1.selectbox("Commodity", APPROVED_COMMODITIES, key="quote_commodity")
    weight = q2.number_input(
        "Estimated weight (tons)", min_value=0.0, value=24.0, step=0.5, key="quote_weight"
    )
    lane_miles = q3.number_input(
        "One-way miles",
        min_value=1.0,
        value=float(DEFAULT_LANE_MILES),
        step=5.0,
        key="quote_miles",
        help="Default ~280 mi for Spruce Pine → Kohler area",
    )

    rate_mode = st.radio(
        "Quote using",
        ["Rate per ton", "Revenue per mile (RPM)"],
        horizontal=True,
        key="quote_rate_mode",
    )

    r1, r2 = st.columns(2)
    if rate_mode == "Rate per ton":
        input_rate = r1.number_input(
            "Target rate per ton ($)",
            min_value=0.0,
            value=float(PRIMARY_LANE["baseline_rate_per_ton"]),
            step=0.25,
            key="quote_rpt",
        )
        input_rpm = (input_rate * weight / lane_miles) if lane_miles > 0 and weight > 0 else 0.0
        r2.metric("Implied RPM", f"${input_rpm:.2f}/mi")
    else:
        input_rpm = r1.number_input(
            "Target RPM ($/loaded mile)",
            min_value=0.0,
            value=4.35,
            step=0.05,
            key="quote_rpm",
        )
        input_rate = (input_rpm * lane_miles / weight) if weight > 0 else 0.0
        r2.metric("Implied rate/ton", f"${input_rate:.2f}")

    deadhead_miles = st.number_input(
        "Est. deadhead miles (return empty)",
        min_value=0.0,
        value=float(DEFAULT_DEADHEAD_MILES),
        step=5.0,
        key="quote_deadhead",
    )

    metrics = compute_quote_metrics(weight, lane_miles, deadhead_miles, input_rate, commodity)
    fit = score_trailer_fit(commodity, weight, "")

    st.divider()
    st.markdown("#### Quote Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Est. total revenue", f"${metrics['revenue']:,.0f}")
    m2.metric("Revenue per mile", f"${metrics['rpm']:.2f}")
    m3.metric("Deadhead cost est.", f"${metrics['deadhead_cost']:,.0f}")
    m4.metric("Net after deadhead", f"${metrics['net_after_deadhead']:,.0f}")

    st.caption(
        f"Deadhead formula: {deadhead_miles:.0f} mi × "
        f"${FUEL_COST_PER_MILE + OPS_COST_PER_MILE:.2f}/mi "
        f"(fuel ${FUEL_COST_PER_MILE:.2f} + ops ${OPS_COST_PER_MILE:.2f}) · "
        f"Margin after deadhead: {metrics['margin_pct']:.0%}"
    )

    if metrics["net_after_deadhead"] < 0:
        st.error("Quoted revenue does not cover estimated deadhead — raise rate or find a backhaul.")
    elif metrics["margin_pct"] < 0.35:
        st.warning("Thin margin after deadhead — confirm fuel and tarp/washout costs.")
    else:
        st.success("Quote clears deadhead with workable margin for a single-truck lane.")

    st.markdown("#### Recommended rate range (this lane / commodity)")
    range_cols = st.columns(3)
    range_cols[0].metric("Floor", f"${metrics['rate_low']:.2f}/ton")
    range_cols[1].metric("Target", f"${metrics['rate_mid']:.2f}/ton")
    range_cols[2].metric("Ceiling", f"${metrics['rate_high']:.2f}/ton")
    st.caption(
        f"Trailer fit: **{fit['level']}** — {fit['reasons'][0] if fit['reasons'] else ''}"
    )

    if st.button("Use these numbers to log a load", type="primary", use_container_width=True):
        prefill_load_logger(
            pickup_date=date.today(),
            shipper_pick="— Free text —",
            shipper="",
            commodity=commodity,
            weight=weight,
            rate_per_ton=round(input_rate, 2),
            total_revenue=metrics["revenue"],
            pricing_mode="Rate per ton",
            status="Quoted",
            destination=destination,
            miles=lane_miles,
            loaded_miles=lane_miles,
            notes=(
                f"Quoted {origin} → {destination} · {lane_miles:.0f} mi · "
                f"${metrics['rpm']:.2f}/mi · deadhead est ${metrics['deadhead_cost']:,.0f}"
            ),
        )

    st.divider()
    with st.expander("Save benchmark to lane_rates"):
        with st.form("save_lane_rate"):
            lane_notes = st.text_input("Lane notes", value=f"Quoted {date.today()}")
            save_submitted = st.form_submit_button("Save Lane Rate", use_container_width=True)
        if save_submitted:
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO lane_rates
                    (origin, destination, commodity, base_rate_per_ton,
                     typical_distance_miles, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    origin,
                    destination,
                    commodity,
                    round(input_rate, 2),
                    int(lane_miles),
                    lane_notes,
                ),
            )
            conn.commit()
            conn.close()
            st.success(f"Saved ${input_rate:.2f}/ton benchmark for {origin} → {destination}")
            st.rerun()

    lane_rates_df = fetch_lane_rates()
    if not lane_rates_df.empty:
        st.markdown("#### Saved Lane Rates")
        st.dataframe(lane_rates_df, use_container_width=True, hide_index=True)


def render_load_board_tab() -> None:
    st.subheader("Load Board")
    st.caption("BulkLoads NC/GA intel · log opportunities · minimize deadhead on Spruce Pine → Kohler")

    from lp_helpers.load_board import (
        NC_GA_MARKET_INTEL,
        fetch_opportunities,
        insert_opportunity,
        upsert_market_intel,
    )

    render_target_lane_banner()

    with st.form("board_opportunity"):
        c1, c2 = st.columns(2)
        lane = c1.text_input(
            "Lane",
            value=f"{PRIMARY_LANE['origin']} → {PRIMARY_LANE['destination']}",
        )
        commodity = c2.selectbox("Commodity", APPROVED_COMMODITIES)
        c3, c4 = st.columns(2)
        rate = c3.text_input("Rate", placeholder="$48/ton")
        contact = c4.text_input("Contact", placeholder="Broker / shipper phone")
        notes = st.text_area("Notes", placeholder="Weight, equipment, pickup window…")
        if st.form_submit_button("Save Opportunity", type="primary", use_container_width=True):
            if lane.strip():
                try:
                    with closing(get_connection()) as conn:
                        insert_opportunity(
                            conn,
                            lane=lane.strip(),
                            commodity=commodity,
                            rate=rate.strip(),
                            contact=contact.strip(),
                            notes=notes.strip(),
                            source="manual",
                        )
                        conn.commit()
                    st.success(f"Saved — {lane}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            else:
                st.error("Lane is required.")

    render_section_header("NC/GA End-Dump Market Intel", icon="📈")
    if st.button("Refresh BulkLoads Intel", use_container_width=True):
        st.session_state.load_board_refreshed = datetime.now().strftime("%Y-%m-%d %H:%M")
        added, updated, errors = 0, 0, 0
        with closing(get_connection()) as conn:
            for item in NC_GA_MARKET_INTEL:
                try:
                    if upsert_market_intel(
                        conn,
                        lane=item["lane"],
                        commodity=item["commodity"],
                        rate=item["rate"],
                        contact=item["contact"],
                        notes=item.get("notes", ""),
                    ):
                        added += 1
                    else:
                        updated += 1
                except Exception as exc:
                    errors += 1
                    log.warning("BulkLoads upsert failed: %s", exc)
            conn.commit()
        msg = f"Intel sync — {added} new, {updated} updated"
        if errors:
            msg += f", {errors} errors (see logs)"
        st.success(msg)
        st.rerun()

    refreshed = st.session_state.get("load_board_refreshed", "Not refreshed this session")
    st.caption(f"Last refresh: {refreshed}")

    for item in NC_GA_MARKET_INTEL:
        st.markdown(
            f"**{item['commodity']}** · {item['lane']} · "
            f"**{item['rate']}** · {item['contact']}  \n"
            f"_{item['notes']}_"
        )

    render_section_header("Saved Opportunities", icon="💼")
    try:
        with closing(get_connection()) as conn:
            opps_df = fetch_opportunities(conn)
    except Exception:
        opps_df = pd.DataFrame()
    if opps_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state(
            "📦",
            "No opportunities yet",
            "Refresh intel or log an opportunity above to get started.",
        )
    else:
        show = [c for c in ["lane", "commodity", "rate", "contact", "source", "created_at"] if c in opps_df.columns]
        st.dataframe(opps_df[show], use_container_width=True, hide_index=True)

        st.markdown("#### Book to Logger")
        labels = [
            f"{r.get('commodity', '?')} — {r.get('lane', '?')}"
            for _, r in opps_df.iterrows()
        ]
        pick = st.selectbox("Opportunity", labels)
        if st.button("Pre-fill Logger", use_container_width=True):
            row = opps_df.iloc[labels.index(pick)].to_dict()
            parts = str(row.get("lane", "")).split("→")
            dest = parts[-1].strip() if len(parts) > 1 else PRIMARY_LANE["destination"]
            prefill_load_logger(
                shipper=row.get("contact", ""),
                commodity=row.get("commodity", "Feldspar"),
                destination=dest,
                notes=row.get("notes", ""),
                status="Potential",
            )


def render_gps_tracking_tab() -> None:
    st.header("Traccar GPS Fleet Tracking")
    st.subheader("Live Truck Locations")
    st.caption(f"{TRUCK_LABEL} · Spruce Pine → Central GA · geofence alerts · sim fallback")

    default_url = get_secret("traccar", "url", "http://localhost:8082")
    default_token = get_secret("traccar", "api_token", "")

    cfg1, cfg2 = st.columns(2)
    traccar_url = cfg1.text_input(
        "Traccar Server URL",
        value=st.session_state.get("traccar_url_input", default_url),
        placeholder="http://your-traccar-server:8082",
        key="traccar_url_input",
    )
    traccar_key = cfg2.text_input(
        "API Token / Key",
        value=st.session_state.get("traccar_api_key_input", default_token),
        type="password",
        placeholder="Bearer token or email:password",
        key="traccar_api_key_input",
    )

    opt1, opt2, opt3 = st.columns(3)
    live_sim = opt1.toggle(
        "Simulation fallback",
        value=st.session_state.get("gps_live_sim", "1") == "1",
        key="gps_sim_toggle",
    )
    save_filter("gps_live_sim", "1" if live_sim else "0")
    opt2.caption("Leave token blank to use email/password from secrets.toml")
    refresh_clicked = opt3.button("Refresh GPS", type="primary", use_container_width=True)

    if refresh_clicked:
        clear_traccar_cache()
        persist_setting("traccar_url", traccar_url.strip())
        if traccar_key.strip():
            persist_setting("traccar_api_token", traccar_key.strip())

    url, token, email, password = _traccar_connection_params()
    traccar = get_traccar_live()

    if refresh_clicked or st.session_state.get("gps_auto_fetch", True):
        conn_status, fleet, devices = _cached_traccar_fleet(url, token, email, password)
    else:
        conn_status, fleet, devices = traccar.connection_status(), [], []

    if "gps_sim_progress" not in st.session_state:
        st.session_state.gps_sim_progress = 0.0
    if live_sim:
        st.session_state.gps_sim_progress = (st.session_state.gps_sim_progress + 0.03) % 1.0

    live_units = [f for f in fleet if f.get("latitude") is not None]
    using_sim = not conn_status.get("ok") or not live_units

    if conn_status.get("ok"):
        st.success(
            f"Connected to Traccar — {len(devices)} device(s), "
            f"{len(live_units)} with live position"
        )
    elif refresh_clicked:
        st.error(f"Connection failed — {conn_status.get('message', 'check Traccar server')}")
    else:
        st.warning(f"Traccar offline — {conn_status.get('message', 'not connected')}")

    if using_sim and live_sim:
        sim_lat, sim_lon, sim_label = interpolate_route(st.session_state.gps_sim_progress)
        primary = {
            "device_name": f"{TRUCK_LABEL} (Sim)",
            "latitude": sim_lat,
            "longitude": sim_lon,
            "speed_mph": 58.0,
            "status": "simulation",
        }
        map_fleet = [primary]
        st.markdown(
            '<span class="lf-gps-badge sim">● SIMULATION</span>',
            unsafe_allow_html=True,
        )
    elif live_units:
        map_fleet = live_units
        st.markdown(
            '<span class="lf-gps-badge live">● LIVE TRACCAR FLEET</span>',
            unsafe_allow_html=True,
        )
    else:
        map_fleet = []
        st.error("No GPS data — check Traccar server or enable simulation fallback.")

    if map_fleet:
        primary = map_fleet[0]
        lat = primary["latitude"]
        lon = primary["longitude"]
        speed = primary.get("speed_mph", 0)
        device_name = primary.get("device_name", TRUCK_LABEL)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Latitude", f"{lat:.5f}")
        m2.metric("Longitude", f"{lon:.5f}")
        m3.metric("Speed", f"{speed:.0f} mph")
        m4.metric("Primary unit", str(device_name)[:22])

        if not using_sim and st.button("Save primary fix to telematics", use_container_width=True):
            try:
                with closing(get_connection()) as conn:
                    traccar.persist_telematics(conn, primary)
                st.success("Position logged to telematics table.")
            except Exception as exc:
                st.error(str(exc))

        geofences = LAWSON_GEOFENCES

        def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            from math import asin, cos, radians, sin, sqrt

            r = 3958.8
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 2 * r * asin(sqrt(a))

        for gf_name, gf_lat, gf_lon, gf_radius_mi in geofences:
            dist = _haversine_mi(lat, lon, gf_lat, gf_lon)
            if dist <= gf_radius_mi:
                st.success(f"Geofence alert: inside **{gf_name}** ({dist:.1f} mi from center)")
                if st.button(f"Log arrival SMS for {gf_name}", key=f"gps_arrival_{gf_name}"):
                    body = format_sms("arrival", {"location": gf_name, "company": "Dispatch"})
                    log_sms_event(None, "geofence_arrival", body, "gps_geofence")
                    st.info("Arrival alert logged — send from **Alerts** tab.")

        if HAS_FOLIUM:
            center_lat = lat
            center_lon = lon
            fmap = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="CartoDB dark_matter")
            route_coords = [(p[0], p[1]) for p in SIM_ROUTE]
            folium.PolyLine(route_coords, color="#ff8c42", weight=4, opacity=0.85).add_to(fmap)
            for gf_name, gf_lat, gf_lon, gf_radius_mi in geofences:
                folium.Circle(
                    [gf_lat, gf_lon],
                    radius=int(gf_radius_mi * 1609),
                    color="#5eead4",
                    fill=True,
                    fill_opacity=0.12,
                    popup=gf_name,
                ).add_to(fmap)
            for unit in map_fleet:
                if unit.get("latitude") is None:
                    continue
                icon_color = "green" if unit.get("status") == "online" else "orange"
                folium.Marker(
                    [unit["latitude"], unit["longitude"]],
                    popup=(
                        f"{unit.get('device_name', 'Truck')} · "
                        f"{unit.get('speed_mph', 0):.0f} mph · {unit.get('status', '?')}"
                    ),
                    icon=folium.Icon(color=icon_color, icon="truck", prefix="fa"),
                ).add_to(fmap)
            st_folium(fmap, width=700, height=500, returned_objects=[])
        else:
            st.warning("Install folium + streamlit-folium for map: pip install folium streamlit-folium")

    if fleet:
        st.markdown("#### Fleet devices")
        fleet_rows = [
            {
                "Name": f.get("device_name"),
                "Status": f.get("status"),
                "Lat": f.get("latitude"),
                "Lon": f.get("longitude"),
                "Speed mph": round(float(f.get("speed_mph") or 0), 1),
            }
            for f in fleet
        ]
        st.dataframe(pd.DataFrame(fleet_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### 🚨 Emergency")
    primary_fix = map_fleet[0] if map_fleet else None
    _render_emergency_controls(
        gps_fix=primary_fix if primary_fix and not using_sim else None,
        key_prefix="gps_em",
    )

    st.info(
        "Setup Traccar self-hosted or cloud for real device tracking. "
        "Add server URL + API token above, or configure `[traccar]` in `.streamlit/secrets.toml`."
    )

    with st.expander("Traccar connection details"):
        st.code(
            f"URL: {url}\n"
            f"Auth: {'API token' if token else f'email {email}'}\n"
            f"Devices: {len(devices)} · Live fixes: {len(live_units)}\n"
            f"Version: {conn_status.get('version', '—')}",
            language="text",
        )


def render_alerts_tab() -> None:
    st.subheader("Alerts")
    st.caption("Twilio SMS · SMTP email · driver emergency numbers · secure secrets.toml")

    _render_emergency_controls(key_prefix="alert_em")

    st.divider()
    with st.expander("Platform Health Check", expanded=False):
        run_platform_health_check()
    st.divider()

    tw_ok = all([
        get_secret("twilio", "account_sid"),
        get_secret("twilio", "auth_token"),
        get_secret("twilio", "from_number"),
    ])
    smtp_ok = all([
        get_secret("smtp", "host"),
        get_secret("smtp", "user"),
        get_secret("smtp", "password"),
    ])
    status_cols = st.columns(2)
    if tw_ok:
        status_cols[0].success("Twilio SMS ready")
    else:
        status_cols[0].warning("Twilio not configured — add [twilio] to secrets.toml")
    if smtp_ok:
        status_cols[1].success("SMTP email ready")
    else:
        status_cols[1].warning("SMTP not configured — add [smtp] to secrets.toml")

    dispatch_phone = st.text_input(
        "Dispatch Phone (E.164)",
        value=get_secret("twilio", "dispatch_phone", "+18284678218"),
        key="twilio_dispatch_phone",
    )
    if dispatch_phone != _local_get_setting("twilio_dispatch_phone", ""):
        persist_setting("twilio_dispatch_phone", dispatch_phone)

    auto_new_load = st.toggle(
        "Auto-send SMS to dispatcher when new load is logged",
        value=st.session_state.get("sms_auto_new_load", "1") == "1",
        key="sms_auto_new_load_toggle",
    )
    save_filter("sms_auto_new_load", "1" if auto_new_load else "0")

    auto_send = st.toggle(
        "Auto-send SMS when load status is Dispatched / In Transit",
        value=st.session_state.get("sms_auto_send", "0") == "1",
        key="sms_auto_toggle",
    )
    save_filter("sms_auto_send", "1" if auto_send else "0")

    if st.button("Send Test Alert", key="twilio_test_alert"):
        try:
            body = "L & P FREIGHT Alert: New load opportunity ready."
            tw_sid = send_twilio_notification(dispatch_phone, body)
            log_sms_event(None, "test_alert", body, "twilio", tw_sid)
            st.success("Test SMS sent!")
        except Exception as exc:
            st.error(str(exc))

    st.markdown("#### Automation Rules")
    st.write("• **New Load Logged** → SMS to dispatcher")
    st.write("• **Load Status Dispatched / In Transit** → SMS to shipper lead")
    st.write("• **BOL Ready** → Logged + optional notify")

    st.divider()

    leads_df = fetch_leads()
    lead_map = {
        f"{row['company']} (ID {row['id']})": row.to_dict()
        for _, row in leads_df.iterrows()
    } if not leads_df.empty else {}

    channel = st.radio("Channel", ["SMS", "Email"], horizontal=True, key="alert_channel")

    n1, n2 = st.columns(2)
    template_keys = list(SMS_TEMPLATES.keys())
    alert_type = n1.selectbox("Template", template_keys, key="notif_template")
    selected = n2.selectbox(
        "Recipient lead",
        list(lead_map.keys()) if lead_map else ["—"],
        key="notif_lead",
    )

    lead = lead_map.get(selected, {"company": "Contact", "phone": "", "email": ""})
    extra = st.text_input(
        "Detail / location",
        value=PRIMARY_LANE["origin"],
        placeholder="On site, ready to load feldspar",
        key="notif_extra",
    )

    context = {
        "company": lead.get("company", "Contact"),
        "location": extra,
        "detail": extra,
        "commodity": "Feldspar",
        "weight_tons": 24.0,
        "origin": PRIMARY_LANE["origin"],
        "destination": PRIMARY_LANE["destination"],
        "rate_per_ton": PRIMARY_LANE["baseline_rate_per_ton"],
        "total_revenue": PRIMARY_LANE["baseline_rate_per_ton"] * 24,
        "bol_number": generate_bol_number(),
        "shipper": lead.get("company", "Shipper"),
        "pickup_date": str(date.today()),
    }
    sms_text = format_sms(alert_type, context)
    email_subject, email_body = format_email(alert_type, context)

    if channel == "SMS":
        st.text_area("SMS preview", sms_text, height=140, key="notif_preview")
    else:
        st.text_input("Email subject", email_subject, key="notif_email_subject")
        st.text_area("Email preview", email_body, height=140, key="notif_email_preview")

    b1, b2, b3 = st.columns(3)
    if b1.button("Copy & log", use_container_width=True):
        logged_msg = sms_text if channel == "SMS" else email_body
        log_sms_event(
            lead.get("id") if isinstance(lead.get("id"), int) else None,
            alert_type,
            logged_msg,
            "clipboard" if channel == "SMS" else "email_clipboard",
        )
        st.success("Logged to alert history.")

    if channel == "SMS":
        test_to = b2.text_input(
            "Send to (E.164)",
            placeholder="+18285550123",
            key="notif_test_to",
            label_visibility="collapsed",
        )
        if b3.button("Send via Twilio", use_container_width=True, type="primary"):
            to_num = test_to.strip() or normalize_phone(str(lead.get("phone", "")).split("|")[0])
            if not to_num:
                st.error("Enter a phone number or select a lead with a phone.")
            else:
                try:
                    tw_sid = send_twilio_notification(to_num, sms_text)
                    log_sms_event(
                        lead.get("id") if isinstance(lead.get("id"), int) else None,
                        alert_type,
                        sms_text,
                        "twilio",
                        tw_sid,
                    )
                    st.success(f"Sent — SID {tw_sid}")
                except Exception as exc:
                    st.error(str(exc))
    else:
        test_email = b2.text_input(
            "Send to (email)",
            placeholder="dispatch@shipper.com",
            key="notif_test_email",
            label_visibility="collapsed",
        )
        if b3.button("Send via SMTP", use_container_width=True, type="primary"):
            to_addr = test_email.strip() or str(lead.get("email", "")).strip()
            if not to_addr:
                st.error("Enter an email or select a lead with an email on file.")
            else:
                try:
                    send_email_notification(to_addr, email_subject, email_body)
                    log_sms_event(
                        lead.get("id") if isinstance(lead.get("id"), int) else None,
                        alert_type,
                        email_body,
                        "smtp",
                    )
                    st.success(f"Email sent to {to_addr}")
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    render_section_header("Alert Log", icon="📋")
    try:
        with closing(get_connection()) as conn:
            sms_df = pd.read_sql_query(
                """
                SELECT s.*, l.company
                FROM sms_log s
                LEFT JOIN leads l ON s.lead_id = l.id
                ORDER BY s.logged_at DESC
                LIMIT 25
                """,
                conn,
            )
        if sms_df.empty:
            from lp_helpers.ui_components import render_empty_state

            render_empty_state("💬", "No messages logged yet.")
        else:
            st.dataframe(sms_df, use_container_width=True, hide_index=True)
    except sqlite3.Error:
        st.caption("SMS log table not initialized — run main app once to init_db().")


def render_bol_generator_tab() -> None:
    st.subheader("BOL")
    st.caption("ReportLab branded PDF Bills of Lading from logged loads.")

    loads_df = fetch_loads()
    if loads_df.empty:
        from lp_helpers.ui_components import render_empty_state

        render_empty_state(
            "📄",
            "No loads logged yet",
            "Log a load in the Logger tab first, then generate a BOL here.",
        )
        return

    options = {
        f"{row['bol_number']} — {row['shipper']} ({row.get('load_date', '')})": row.to_dict()
        for _, row in loads_df.iterrows()
    }
    selected_key = st.selectbox("Select load", list(options.keys()))
    load = options[selected_key]

    preview1, preview2 = st.columns(2)
    with preview1:
        st.markdown(f"**Shipper:** {load.get('shipper', '—')}")
        st.markdown(f"**Commodity:** {load.get('commodity', '—')}")
        st.markdown(f"**Weight:** {load.get('weight_tons', '—')} tons")
    with preview2:
        st.markdown(f"**Route:** {load.get('origin', TARGET_LANE_ORIGIN)} → {load.get('destination', '—')}")
        st.markdown(f"**Revenue:** ${float(load.get('total_revenue', 0)):,.2f}")
        st.markdown(f"**Status:** {load.get('status', 'Logged')}")

    pdf_name = bol_pdf_filename(load)

    if st.button("Generate PDF BOL", type="primary", use_container_width=True):
        bol_errors = validate_bol_load(load)
        if bol_errors:
            for err in bol_errors:
                st.error(err)
        else:
            try:
                pdf_bytes = generate_bol_pdf(load)
                st.session_state["bol_pdf_bytes"] = pdf_bytes
                st.session_state["bol_pdf_name"] = pdf_name
                ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                out_path = ATTACHMENTS_DIR / pdf_name
                out_path.write_bytes(pdf_bytes)
                bol_msg = format_sms("bol_ready", load)
                log_sms_event(None, "bol_ready", bol_msg, "generated")
                st.success(f"BOL generated — saved to attachments/{pdf_name}")
                if st.session_state.get("sms_auto_send") == "1":
                    st.info("BOL ready notification logged. Enable Twilio to auto-send.")
            except OSError as exc:
                log.exception("BOL file write failed")
                st.error(f"Could not save BOL file: {exc}")
            except Exception as exc:
                log.exception("BOL generation failed")
                st.error(f"BOL generation failed: {exc}")

    if (
        st.session_state.get("bol_pdf_bytes")
        and st.session_state.get("bol_pdf_name") == pdf_name
    ):
        st.download_button(
            "Download PDF BOL",
            st.session_state["bol_pdf_bytes"],
            pdf_name,
            mime="application/pdf",
            use_container_width=True,
        )


def _driver_view_requested() -> bool:
    try:
        if st.query_params.get("view") == "driver":
            return True
    except Exception:
        pass
    return st.session_state.get("view_mode") == "driver"


def _exit_driver_view() -> None:
    st.session_state.view_mode = "dispatch"
    try:
        st.query_params.clear()
    except Exception:
        pass


def safe_render_driver_view() -> None:
    """Crash-proof Driver View — signature-tolerant, never takes down Dispatch."""
    try:
        from lp_helpers.driver_mobile import render_driver_app

        def _traccar_status_for_driver() -> dict[str, Any] | None:
            try:
                url, token, email, password = _traccar_connection_params()
                status, _fleet, _devices = _cached_traccar_fleet(url, token, email, password)
                if status.get("ok"):
                    return get_traccar_live().get_live_status(None)
            except Exception:
                return None
            return None

        def _on_exit() -> None:
            st.session_state.view_mode = "dispatch"
            try:
                st.query_params.clear()
            except Exception:
                pass

        # Pass full kwargs; render_driver_app accepts optional GPS + ignores extras
        render_driver_app(
            get_connection=get_connection,
            get_active_owner=get_active_owner,
            truck_label=TRUCK_LABEL,
            get_traccar_status=_traccar_status_for_driver,
            format_sms=format_sms,
            log_sms_event=log_sms_event,
            on_emergency=dispatch_emergency,
            on_exit=_on_exit,
        )
    except Exception as e:
        st.error("Driver View is temporarily unavailable.")
        st.caption(f"Error: {str(e)[:120]}")
        if st.button("Return to Dispatch View", use_container_width=True, key="driver_return_safe"):
            st.session_state.view_mode = "dispatch"
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()


def apply_platform_theme(night_mode: bool | None = None) -> None:
    """Complete consistent theming — delegates to lp_helpers.ui_theme."""
    try:
        from lp_helpers.ui_theme import apply_platform_theme as _apply

        _apply(night_mode)
        return
    except Exception:
        pass
    if night_mode is None:
        if "night_mode" not in st.session_state:
            st.session_state.night_mode = True
        night = bool(st.session_state.night_mode)
    else:
        night = bool(night_mode)
        st.session_state.night_mode = night
    if night:
        st.markdown(
            """
            <style>
            .stApp { background-color: #0b1120 !important; color: #f1f5f9 !important; }
            section[data-testid="stSidebar"] { background-color: #1e2937 !important; }
            .stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox > div > div {
                background-color: #1e2937 !important; color: #e0e7ff !important;
                border: 2px solid #475569 !important; -webkit-text-fill-color: #e0e7ff !important;
            }
            .stButton > button { background: linear-gradient(135deg, #1e40af, #3b82f6) !important;
                color: #ffffff !important; font-weight: 700 !important; min-height: 48px !important; }
            button[kind="secondary"] { background-color: #1e2937 !important; color: #f1f5f9 !important; border: 2px solid #475569 !important; }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #bae6fd !important; font-size: 1.6rem !important; font-weight: 800 !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            .stApp { background-color: #f8fafc !important; color: #0f172a !important; }
            section[data-testid="stSidebar"] { background-color: #e2e8f0 !important; }
            .stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox > div > div {
                background-color: #ffffff !important; color: #0f172a !important;
                border: 2px solid #cbd5e1 !important; -webkit-text-fill-color: #0f172a !important;
            }
            .stButton > button { background: linear-gradient(135deg, #1e40af, #3b82f6) !important;
                color: #ffffff !important; font-weight: 700 !important; min-height: 48px !important; }
            button[kind="secondary"] { background-color: #f1f5f9 !important; color: #0f172a !important; border: 2px solid #cbd5e1 !important; }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #1e40af !important; font-size: 1.6rem !important; font-weight: 800 !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )


def render_sidebar_brand(
    carrier: str = "L & P Dispatch",
    lane_origin: str = "Spruce Pine, NC",
    lane_dest: str = "Central Georgia (Kohler area)",
    trailer: str = "39ft Frameless End-Dump",
) -> None:
    """Safe fallback sidebar brand header."""
    try:
        st.sidebar.markdown(f"### {carrier}")
        st.sidebar.caption(f"{lane_origin} -> {lane_dest} · {trailer}")
        st.sidebar.caption("Owner-operator & small-fleet dispatch")
    except Exception:
        pass


def render_day_night_toggle():
    """Reliable Day/Night mode toggle with immediate theme update (fallback path)."""
    if "night_mode" not in st.session_state:
        saved = _local_get_setting("night_mode", "true")
        st.session_state.night_mode = str(saved).lower() in ("1", "true", "yes")

    toggle_label = "Night Mode" if st.session_state.night_mode else "Day Mode"

    toggle = st.sidebar.toggle(
        toggle_label,
        value=st.session_state.night_mode,
        key="night_mode_toggle_fallback",
    )

    if toggle != st.session_state.night_mode:
        st.session_state.night_mode = toggle
        try:
            _local_set_setting("night_mode", "true" if toggle else "false")
        except Exception:
            pass
        st.rerun()

    apply_platform_theme(bool(st.session_state.night_mode))


def main() -> None:
    auto_backup_db()

    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon="🚛",
        layout="wide",
    )

    # === Initialize Session State Persistence ===
    try:
        from lp_helpers.fleet_context import ensure_session_tenant

        ensure_session_tenant()
    except Exception:
        st.session_state.setdefault("tenant_id", "lp-freight")

    if "owner_role" not in st.session_state:
        st.session_state["owner_role"] = get_active_owner()

    if "night_mode" not in st.session_state:
        try:
            saved = _local_get_setting("night_mode", "true")
            st.session_state.night_mode = str(saved).lower() in ("1", "true", "yes")
        except Exception:
            st.session_state.night_mode = True

    # Solo fleets: implied owner_driver role (multi-user later)
    st.session_state.setdefault("user_role", "owner_driver")

    apply_platform_theme(bool(st.session_state.night_mode))

    load_persistent_filters()

    # === DRIVER VIEW EARLY EXIT (before dispatch chrome) ===
    if _driver_view_requested():
        try:
            from lp_helpers.database import init_db

            init_db()
        except Exception:
            init_database()
        else:
            init_database()
        safe_render_driver_view()
        st.stop()

    try:
        from lp_helpers.mobile_web import (
            inject_mobile_css,
            inject_mobile_shell_js,
            inject_pwa_head,
        )

        inject_pwa_head()
        inject_mobile_css()
        inject_mobile_shell_js()
    except ImportError:
        pass

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"
    if st.session_state.active_tab not in TAB_KEYS:
        st.session_state.active_tab = "Dashboard"

    night_mode = bool(st.session_state.get("night_mode", True))
    try:
        from lp_helpers.database import init_db
        from lp_helpers.ui_components import inject_road_css, is_night_mode

        init_db()
        init_database()
        render_sidebar()
        night_mode = is_night_mode()
        inject_road_css(night_mode)
        if night_mode:
            inject_elite_dark_css()
    except ImportError:
        init_database()
        render_sidebar()
        night_mode = bool(st.session_state.get("night_mode", True))

    # Final theme pass — wins over inject_road_css for text pop + contrast
    apply_platform_theme(night_mode)

    st.title(f"🚛 {PLATFORM_TITLE}")
    st.caption(f"{TAGLINE} · {TRAILER_DESC} · {APP_VERSION} · `{DB_PATH.name}`")

    nav_hint = st.session_state.pop("nav_hint", None)
    if nav_hint:
        st.info(nav_hint)

    active = render_main_nav()

    if active == "Dashboard":
        render_dashboard_tab()
    elif active == "Leads":
        render_leads_crm_tab()
    elif active == "Logger":
        render_load_logger_tab()
    elif active == "Board":
        render_load_board_tab()
    elif active == "GPS":
        render_gps_tracking_tab()
    elif active == "BOL":
        render_bol_generator_tab()
    elif active == "Alerts":
        render_alerts_tab()
    else:
        render_dashboard_tab()

    st.caption(f"{CARRIER_NAME} · {TAGLINE}")



if __name__ == "__main__":
    main()