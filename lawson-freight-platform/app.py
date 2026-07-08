"""
L & P Dispatch — Lawson Freight Platform.
Optimized for Phillip & Lawson: Spruce Pine NC → Kohler GA · 39ft end-dump · mineral lane.
"""

from __future__ import annotations

import logging
import re
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
APP_VERSION = "4.2 Lawson"

try:
    from lp_helpers.lawson_profile import (
        CARRIER_NAME,
        DEFAULT_OWNER,
        DRIVERS,
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
    CARRIER_NAME = "L & P Dispatch"
    PLATFORM_TITLE = "L & P Dispatch — Lawson Freight"
    PAGE_TITLE = "L & P Dispatch | Lawson Freight"
    TAGLINE = "Spruce Pine NC → Central GA · Phillip & Lawson"
    MISSION_BLURB = (
        "Build loaded miles Spruce Pine NC → Central Georgia (Kohler area). "
        "Minimize deadhead on Hwy 19E & 226."
    )
    DEFAULT_OWNER = "Phillip"
    DRIVERS = ("Phillip", "Lawson")
    TRUCK_LABEL = "L&P Lawson End-Dump"
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

TAB_OPTIONS = [
    "Dashboard",
    "Leads",
    "Logger",
    "GPS",
    "BOL",
    "Alerts",
    "Rates",
]

FILTER_DEFAULTS: dict[str, str] = {
    "filter_leads_status": "All",
    "filter_loads_status": "All",
    "filter_leads_search": "",
    "filter_loads_search": "",
    "gps_live_sim": "1",
    "sms_auto_send": "0",
}

SIM_ROUTE: list[tuple[float, float, str]] = LAWSON_SIM_ROUTE

SMS_TEMPLATES: dict[str, str] = {
    "arrival": (
        "L & P FREIGHT | ARRIVAL\n"
        "{company}\n"
        "On site: {location}\n"
        "Driver: {driver} · 39ft end-dump\n"
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
    """Current operator — Phillip or Lawson (persisted in app_settings)."""
    try:
        from lp_helpers.ui_components import get_owner_role

        role = get_owner_role()
        return role if role in DRIVERS else DEFAULT_OWNER
    except ImportError:
        return _local_get_setting("owner_role", DEFAULT_OWNER) or DEFAULT_OWNER


def set_active_owner(role: str) -> None:
    if role not in DRIVERS:
        return
    persist_setting("owner_role", role)


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
        "driver": get_active_owner(),
    }
    defaults.update(context)
    if "driver" not in context:
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
        "Driver: Phillip · 39ft frameless end-dump\n"
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


class TraccarClient:
    """Traccar REST client with graceful simulation fallback."""

    def __init__(self) -> None:
        self.base_url = get_secret("traccar", "url", "http://localhost:8082").rstrip("/")
        self.email = get_secret("traccar", "email", "admin")
        self.password = get_secret("traccar", "password", "admin")
        self._session = requests.Session() if requests else None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and requests is not None)

    def _login(self) -> None:
        if not self._session:
            raise RuntimeError("requests package not installed")
        resp = self._session.post(
            f"{self.base_url}/api/session",
            data={"email": self.email, "password": self.password},
            timeout=8,
        )
        resp.raise_for_status()

    def fetch_positions(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            self._login()
            resp = self._session.get(f"{self.base_url}/api/positions", timeout=8)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as exc:
            log.info("Traccar unavailable (%s) — using simulation", exc)
            return []

    def fetch_devices(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        try:
            self._login()
            resp = self._session.get(f"{self.base_url}/api/devices", timeout=8)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


@st.cache_resource(show_spinner=False)
def get_traccar_client() -> TraccarClient:
    return TraccarClient()


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
        }
        .stApp { background: var(--lf-bg) !important; }
        div[data-testid="stMetric"] label { color: var(--lf-muted) !important; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: var(--lf-text) !important;
        }
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox > div > div {
            background: #1a2436 !important;
            color: var(--lf-text) !important;
            border-color: var(--lf-border) !important;
        }
        .stDataFrame { border: 1px solid var(--lf-border); border-radius: 10px; }
        .lf-gps-badge {
            display: inline-block; padding: 0.25rem 0.65rem; border-radius: 20px;
            font-size: 0.75rem; font-weight: 700; margin-right: 0.5rem;
        }
        .lf-gps-badge.live { background: #064e3b; color: #6ee7b7; }
        .lf-gps-badge.sim { background: #422006; color: #fdba74; }
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


@st.cache_data(ttl=30, show_spinner=False)
def fetch_leads() -> pd.DataFrame:
    try:
        with closing(get_connection()) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM leads ORDER BY priority, company",
                conn,
            )
        if not df.empty:
            df["notes"] = df["lane_notes"].fillna("")
        return df
    except Exception as exc:
        log.exception("fetch_leads failed")
        st.error(f"Could not load leads: {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def fetch_loads() -> pd.DataFrame:
    try:
        with closing(get_connection()) as conn:
            return pd.read_sql_query(
                """
                SELECT *, pickup_date AS load_date
                FROM loads
                ORDER BY pickup_date DESC, id DESC
                """,
                conn,
            )
    except Exception as exc:
        log.exception("fetch_loads failed")
        st.error(f"Could not load loads: {exc}")
        return pd.DataFrame()


def fetch_lane_rates() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM lane_rates ORDER BY origin, destination, commodity",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=30, show_spinner=False)
def fetch_call_logs() -> pd.DataFrame:
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
    loaded = float(loads_df["loaded_miles"].fillna(miles_col).fillna(0).sum())
    total_miles = float(loads_df["miles"].fillna(0).sum())
    deadhead = float(loads_df["deadhead_miles"].fillna(0).sum())
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
    pdf.cell(0, 10, "Lawson Freight Platform — BIG E", ln=True)
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
    st.session_state.active_tab = tab_name
    st.session_state.main_navigation = tab_name
    st.rerun()


def render_lawson_sidebar_extras() -> None:
    """Owner role + Lawson lane context in sidebar."""
    owner = st.selectbox(
        "Operating as",
        list(DRIVERS),
        index=list(DRIVERS).index(get_active_owner())
        if get_active_owner() in DRIVERS
        else 0,
        key="lawson_owner_role",
    )
    if owner != get_active_owner():
        set_active_owner(owner)
        st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Mission Control")
        st.markdown(f"**{CARRIER_NAME}**")
        st.write("**Spruce Pine NC → Central GA**")
        st.write(f"**{TRAILER_DESC}**")
        render_lawson_sidebar_extras()
        st.divider()
        st.markdown(f"**Corridor:** {HIGHWAY_CORRIDORS}")
        st.markdown(f"**Receiver:** {PRIMARY_RECEIVER}")
        st.divider()
        st.subheader("Trailer Specs")
        st.markdown("- **Type:** 39 ft frameless end-dump")
        st.markdown("- **Rated capacity:** ~24 tons")
        st.divider()
        st.subheader("Approved Commodities")
        for commodity in APPROVED_COMMODITIES[:8]:
            st.markdown(f"- {commodity}")
        st.divider()
        st.caption(f"Database: `{DB_PATH.name}`")
        st.caption(f"{TAGLINE} · {datetime.now().strftime('%Y-%m-%d %H:%M')}")


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
            "color:#e85d04;padding:0.25rem 0;'>➜ TARGET LANE ➜</div>",
            unsafe_allow_html=True,
        )
    with lane_col3:
        st.markdown(
            f"<div style='text-align:left;font-size:1.1rem;font-weight:700;'>"
            f"🏁 {TARGET_LANE_DESTINATION}</div>",
            unsafe_allow_html=True,
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
        help=f"Lawson target ≥ {LOADED_MILE_TARGET:.0%} on Spruce Pine → Kohler lane",
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

    st.markdown("#### Quick Actions")
    action1, action2, action3, action4 = st.columns(4)
    if action1.button("Log New Call / Update Lead", use_container_width=True):
        navigate_to_tab("Leads")
    if action2.button("Log Potential Load", use_container_width=True):
        navigate_to_tab("Logger")
    if action3.button("Open Rate Calculator", use_container_width=True):
        navigate_to_tab("Rates")
    if action4.button("Generate BOL", use_container_width=True):
        navigate_to_tab("BOL")

    st.divider()
    st.markdown("#### Analytics")

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
        st.caption("Log loads to unlock Plotly revenue and deadhead charts.")
    else:
        st.caption("Install plotly for interactive dashboard charts: pip install plotly")

    st.divider()
    st.markdown("#### Recent Activity")

    activity_left, activity_right = st.columns(2)

    with activity_left:
        st.markdown("**Last 5 Loads**")
        if loads_df.empty:
            st.caption("No loads logged yet.")
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
            st.caption("No leads in CRM.")
        else:
            notes_df = leads_df.copy()
            notes_df["notes"] = notes_df["notes"].fillna("").astype(str)
            notes_df = notes_df[notes_df["notes"].str.strip() != ""]
            if notes_df.empty:
                st.caption("No lead notes recorded yet.")
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


def render_leads_crm_tab() -> None:
    st.subheader("Leads")
    st.caption("Log calls, update status, and track Spruce Pine shipper outreach.")

    leads_df = fetch_leads()
    if leads_df.empty:
        st.warning("No leads found. Database will seed hot leads on next refresh.")
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

    st.markdown("#### All Leads")
    display_df = filtered[
        [c for c in ["company", "phone", "commodity_focus", "status", "last_contact", "notes"] if c in filtered.columns]
    ]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Log New Call / Update Lead")

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
            fetch_leads.clear()
            fetch_call_logs.clear()
            st.success(f"Updated {lead_row['company']} — status: {new_status}")
            st.rerun()
        except sqlite3.Error as exc:
            log.exception("Save lead failed")
            st.error(f"Could not save lead update: {exc}")

    st.divider()
    st.markdown("#### Recent Calls")
    calls_df = fetch_call_logs()
    if calls_df.empty:
        st.caption("No calls logged yet.")
    else:
        call_cols = [c for c in ["logged_at", "company", "call_type", "outcome", "notes"] if c in calls_df.columns]
        st.dataframe(calls_df[call_cols].head(10), use_container_width=True, hide_index=True)


def render_load_logger_tab() -> None:
    st.subheader("Logger")
    render_target_lane_banner()

    prefill = st.session_state.pop("load_prefill", {})
    if prefill:
        apply_load_prefill(prefill)
        st.success("Rate Calculator values loaded — review and save when ready.")

    leads_df = fetch_leads()
    shipper_options = ["— Free text —"] + (
        leads_df["company"].tolist() if not leads_df.empty else []
    )

    commodity_options = list(APPROVED_COMMODITIES)
    prefill_commodity = prefill.get("commodity", "Feldspar")
    if prefill_commodity not in commodity_options:
        prefill_commodity = "Other"

    st.markdown("#### Log New Load")
    row1a, row1b = st.columns(2)
    pickup = row1a.date_input(
        "Date",
        value=prefill.get("pickup_date", date.today()),
        key="load_pickup_date",
    )
    load_status = row1b.selectbox(
        "Status",
        LOAD_STATUS_OPTIONS,
        index=LOAD_STATUS_OPTIONS.index(prefill.get("status", "Potential"))
        if prefill.get("status") in LOAD_STATUS_OPTIONS
        else 0,
        key="load_status",
    )

    row2a, row2b = st.columns(2)
    default_shipper_pick = prefill.get("shipper_pick", "— Free text —")
    if default_shipper_pick not in shipper_options:
        default_shipper_pick = "— Free text —"
    shipper_pick = row2a.selectbox(
        "Shipper",
        shipper_options,
        index=shipper_options.index(default_shipper_pick),
        key="load_shipper_pick",
    )
    commodity = row2b.selectbox(
        "Commodity",
        commodity_options,
        index=commodity_options.index(prefill_commodity),
        key="load_commodity",
    )

    shipper = ""
    if shipper_pick == "— Free text —":
        shipper = st.text_input(
            "Shipper name",
            value=prefill.get("shipper", ""),
            placeholder="Enter shipper / broker name",
            key="load_shipper_text",
        )
    else:
        shipper = shipper_pick

    commodity_final = commodity
    if commodity == "Other":
        commodity_final = st.text_input(
            "Specify commodity",
            value=prefill.get("commodity_other", prefill.get("commodity", "")),
            placeholder="e.g. Crushed glass (washout required)",
            key="load_commodity_other",
        )

    row3a, row3b, row3c = st.columns(3)
    weight = row3a.number_input(
        "Weight (tons)",
        min_value=0.0,
        max_value=30.0,
        value=float(prefill.get("weight", 24.0)),
        step=0.5,
        key="load_weight",
    )
    pricing_mode = row3b.selectbox(
        "Price by",
        ["Rate per ton", "Total revenue"],
        index=0 if prefill.get("pricing_mode", "Rate per ton") == "Rate per ton" else 1,
        key="load_pricing_mode",
    )
    if pricing_mode == "Rate per ton":
        rate_input = row3c.number_input(
            "Rate per ton ($)",
            min_value=0.0,
            value=float(prefill.get("rate_per_ton", PRIMARY_LANE["baseline_rate_per_ton"])),
            step=0.25,
            key="load_rate_per_ton",
        )
        revenue_input = 0.0
    else:
        revenue_input = row3c.number_input(
            "Total revenue ($)",
            min_value=0.0,
            value=float(prefill.get("total_revenue", 0.0)),
            step=1.0,
            key="load_total_revenue",
        )
        rate_input = 0.0

    destination = st.text_input(
        "Destination",
        value=prefill.get("destination", PRIMARY_LANE["destination"]),
        placeholder=f"{PRIMARY_RECEIVER} / Kohler area",
        key="load_destination",
    )
    notes = st.text_area(
        "Notes",
        value=prefill.get("notes", ""),
        placeholder="Potential pickup window, tarp, washout, scale instructions…",
        key="load_notes",
    )

    preview_commodity = commodity_final or commodity
    rate_preview, revenue_preview = resolve_rate_and_revenue(
        weight, rate_input if pricing_mode == "Rate per ton" else None,
        revenue_input if pricing_mode == "Total revenue" else None,
        pricing_mode,
    )
    fit = score_trailer_fit(preview_commodity, weight, notes)

    st.markdown("#### Trailer Fit Score")
    fit_cols = st.columns([1, 3])
    level = fit["level"]
    if level == "High":
        fit_cols[0].success(f"**{level}**")
    elif level == "Medium":
        fit_cols[0].warning(f"**{level}**")
    else:
        fit_cols[0].error(f"**{level}**")
    fit_cols[1].markdown(
        " · ".join(fit["reasons"])
        + (f" · Est. **${rate_preview:.2f}/ton** · **${revenue_preview:,.0f}** total"
           if rate_preview > 0 else "")
    )

    submitted = st.button("Save Load", type="primary", use_container_width=True, key="save_load_btn")

    if submitted:
        if not shipper or not str(shipper).strip():
            st.error("Shipper is required.")
        elif not preview_commodity or not str(preview_commodity).strip():
            st.error("Commodity is required.")
        elif weight <= 0:
            st.error("Weight must be greater than zero.")
        elif rate_preview <= 0 or revenue_preview <= 0:
            st.error("Enter a valid rate per ton or total revenue.")
        elif weight > TRAILER_MAX_TONS:
            st.error(f"Weight exceeds {TRAILER_MAX_TONS}-ton trailer limit.")
        else:
            miles = float(
                st.session_state.get("_load_prefill_miles", DEFAULT_LANE_MILES)
            )
            loaded_miles = float(
                st.session_state.get("_load_prefill_loaded_miles", miles)
            )
            deadhead = max(0.0, miles - loaded_miles)
            bol = generate_bol_number()
            try:
                with closing(get_connection()) as conn:
                    conn.execute(
                        """
                        INSERT INTO loads (
                            bol_number, shipper, commodity, weight_tons, miles,
                            loaded_miles, deadhead_miles, pickup_date, origin, destination,
                            rate_per_ton, total_revenue, notes, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bol,
                            shipper.strip(),
                            preview_commodity.strip(),
                            weight,
                            miles,
                            loaded_miles,
                            deadhead,
                            str(pickup),
                            PRIMARY_LANE["origin"],
                            destination,
                            rate_preview,
                            revenue_preview,
                            notes,
                            load_status,
                        ),
                    )
                    conn.commit()
            except sqlite3.Error as exc:
                log.exception("Save load failed")
                st.error(f"Could not save load: {exc}")
                return
            fetch_loads.clear()
            saved_load = {
                "bol_number": bol,
                "shipper": shipper.strip(),
                "commodity": preview_commodity.strip(),
                "weight_tons": weight,
                "destination": destination,
                "status": load_status,
                "origin": PRIMARY_LANE["origin"],
            }
            lead_phone = None
            if not leads_df.empty:
                match = leads_df[leads_df["company"].astype(str).str.lower() == shipper.strip().lower()]
                if not match.empty:
                    lead_phone = str(match.iloc[0].get("phone", ""))
            maybe_auto_notify_load(saved_load, lead_phone)
            st.success(
                f"Load saved — {load_status} · BOL {bol} · "
                f"${revenue_preview:,.2f} · {level} trailer fit"
            )
            st.rerun()

    st.divider()
    st.markdown("#### Recent Logged Loads")
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
        st.caption("No loads logged yet.")
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


def render_rate_calculator_tab() -> None:
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


def render_gps_tracking_tab() -> None:
    st.subheader("GPS")
    st.caption("Traccar live positions · geofence alerts · Spruce Pine → Central GA simulation")

    client = get_traccar_client()
    live_sim = st.toggle(
        "Live route simulation",
        value=st.session_state.get("gps_live_sim", "1") == "1",
        key="gps_sim_toggle",
    )
    save_filter("gps_live_sim", "1" if live_sim else "0")

    if "gps_sim_progress" not in st.session_state:
        st.session_state.gps_sim_progress = 0.0
    if live_sim:
        st.session_state.gps_sim_progress = (st.session_state.gps_sim_progress + 0.03) % 1.0

    positions = client.fetch_positions()
    devices = client.fetch_devices()
    using_sim = not positions

    if using_sim:
        lat, lon, location_label = interpolate_route(st.session_state.gps_sim_progress)
        speed = 58.0
        device_name = f"{TRUCK_LABEL} (Sim)"
        st.markdown(
            '<span class="lf-gps-badge sim">● SIMULATION</span>',
            unsafe_allow_html=True,
        )
    else:
        pos = positions[0]
        lat = float(pos.get("latitude", SIM_ROUTE[0][0]))
        lon = float(pos.get("longitude", SIM_ROUTE[0][1]))
        speed = float(pos.get("speed", 0)) * 1.15078  # knots → mph approx
        device_name = str(pos.get("deviceId", "Traccar device"))
        location_label = f"Device {device_name}"
        st.markdown(
            '<span class="lf-gps-badge live">● LIVE TRACCAR</span>',
            unsafe_allow_html=True,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Latitude", f"{lat:.5f}")
    m2.metric("Longitude", f"{lon:.5f}")
    m3.metric("Speed", f"{speed:.0f} mph")
    m4.metric("Location", location_label[:28])

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
        center_lat = (SIM_ROUTE[0][0] + SIM_ROUTE[-1][0]) / 2
        center_lon = (SIM_ROUTE[0][1] + SIM_ROUTE[-1][1]) / 2
        fmap = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="CartoDB dark_matter")
        route_coords = [(p[0], p[1]) for p in SIM_ROUTE]
        folium.PolyLine(route_coords, color="#ff8c42", weight=4, opacity=0.85).add_to(fmap)
        for p_lat, p_lon, p_label in SIM_ROUTE:
            folium.CircleMarker(
                [p_lat, p_lon], radius=5, color="#7dd3fc", fill=True, popup=p_label
            ).add_to(fmap)
        for gf_name, gf_lat, gf_lon, gf_radius_mi in geofences:
            folium.Circle(
                [gf_lat, gf_lon],
                radius=int(gf_radius_mi * 1609),
                color="#5eead4",
                fill=True,
                fill_opacity=0.12,
                popup=gf_name,
            ).add_to(fmap)
        folium.Marker(
            [lat, lon],
            popup=f"{device_name} @ {speed:.0f} mph",
            icon=folium.Icon(color="orange", icon="truck", prefix="fa"),
        ).add_to(fmap)
        st_folium(fmap, width=None, height=420, returned_objects=[])
    else:
        st.warning("Install folium + streamlit-folium for interactive map: pip install folium streamlit-folium")
        render_target_lane_banner()

    with st.expander("Traccar connection"):
        st.code(
            f"URL: {client.base_url}\nEmail: {client.email}\n"
            f"Devices: {len(devices)} · Positions: {len(positions)}",
            language="text",
        )
        if st.button("Refresh GPS", use_container_width=True):
            st.session_state.gps_sim_progress = (st.session_state.gps_sim_progress + 0.1) % 1.0
            st.rerun()


def render_alerts_tab() -> None:
    st.subheader("Alerts")
    st.caption("Twilio SMS · SMTP email · auto-send on dispatch · secure secrets.toml")

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

    auto_send = st.toggle(
        "Auto-send SMS when load status is Dispatched / In Transit",
        value=st.session_state.get("sms_auto_send", "0") == "1",
        key="sms_auto_toggle",
    )
    save_filter("sms_auto_send", "1" if auto_send else "0")

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
    st.markdown("#### Alert Log")
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
            st.caption("No messages logged yet.")
        else:
            st.dataframe(sms_df, use_container_width=True, hide_index=True)
    except sqlite3.Error:
        st.caption("SMS log table not initialized — run main app once to init_db().")


def render_bol_generator_tab() -> None:
    st.subheader("BOL")
    st.caption("ReportLab branded PDF Bills of Lading from logged loads.")

    loads_df = fetch_loads()
    if loads_df.empty:
        st.info("No loads logged yet. Log a load in **Logger** first.")
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


def main() -> None:
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon="🚛",
        layout="wide",
    )

    load_persistent_filters()

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"
    if st.session_state.active_tab not in TAB_OPTIONS:
        st.session_state.active_tab = "Dashboard"

    night_mode = False
    try:
        from lp_helpers.database import init_db
        from lp_helpers.ui_components import inject_road_css, is_night_mode, render_day_night_toggle

        init_db()
        night_mode = is_night_mode()
        with st.sidebar:
            st.markdown('<div class="nav-group-label">Mission Control</div>', unsafe_allow_html=True)
            st.markdown(f"**{CARRIER_NAME}**")
            st.write("**Spruce Pine NC → Central GA**")
            st.write(f"**{TRAILER_DESC}**")
            render_lawson_sidebar_extras()
            st.markdown('<div class="nav-group-label">Display</div>', unsafe_allow_html=True)
            render_day_night_toggle()
            st.caption(f"{APP_VERSION} · {get_active_owner()} · GPS · Alerts")
        inject_road_css()
        if night_mode:
            inject_elite_dark_css()
    except ImportError:
        init_database()
        render_sidebar()
    else:
        init_database()

    st.title(PLATFORM_TITLE)
    st.caption(f"{TAGLINE} · {TRAILER_DESC} · {APP_VERSION} · {DB_PATH.name}")

    selected_tab = st.radio(
        "Navigation",
        TAB_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        index=TAB_OPTIONS.index(st.session_state.active_tab),
        key="main_navigation",
    )
    st.session_state.active_tab = selected_tab

    if selected_tab == "Dashboard":
        render_dashboard_tab()
    elif selected_tab == "Leads":
        render_leads_crm_tab()
    elif selected_tab == "Logger":
        render_load_logger_tab()
    elif selected_tab == "Rates":
        render_rate_calculator_tab()
    elif selected_tab == "BOL":
        render_bol_generator_tab()
    elif selected_tab == "GPS":
        render_gps_tracking_tab()
    elif selected_tab == "Alerts":
        render_alerts_tab()

    st.caption(f"{CARRIER_NAME} — optimized for Phillip & Lawson · local-first · {DB_PATH.name}")


if __name__ == "__main__":
    main()