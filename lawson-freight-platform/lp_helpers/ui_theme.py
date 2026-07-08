"""Clean, readable UI theme for L & P Freight Platform."""

from __future__ import annotations

import streamlit as st

# (display label, internal page key, icon)
NAV_PRIMARY: list[tuple[str, str, str]] = [
    ("Home", "Dashboard", "🏠"),
    ("Log a Load", "Load Logger", "📋"),
    ("Load Board", "Load Board", "📦"),
    ("Leads", "Leads & Calls", "📞"),
    ("Analytics", "Analytics", "📉"),
    ("Rates", "AI Intelligence", "💰"),
    ("BOL & Reports", "Reports", "📄"),
]

NAV_MORE: list[tuple[str, str, str]] = [
    ("Geofence", "Geofence Dispatch", "📍"),
    ("SMS Alerts", "SMS Alerts", "💬"),
    ("Documents", "Documents", "📷"),
    ("Insights", "Insights", "💡"),
    ("Fuel & Miles", "Telematics & Fuel", "⛽"),
    ("Maintenance", "Maintenance", "🔧"),
    ("Compliance", "Compliance", "✅"),
    ("Settings", "Settings", "⚙️"),
]

ALL_NAV_KEYS: list[str] = [item[1] for item in NAV_PRIMARY + NAV_MORE]


def inject_ui_css(night_mode: bool = False) -> None:
    """Apply simplified, high-contrast stylesheet."""
    if night_mode:
        vars_css = """
            --lf-bg: #0f1419;
            --lf-card: #1a2332;
            --lf-text: #f1f5f9;
            --lf-muted: #94a3b8;
            --lf-border: #2d3f56;
            --lf-navy: #0f172a;
            --lf-orange: #fb923c;
            --lf-orange-hover: #f97316;
            --lf-blue: #60a5fa;
            --lf-green: #4ade80;
            --lf-amber: #fbbf24;
            --lf-red: #f87171;
            --lf-sidebar: #0a0f16;
            --lf-shadow: rgba(0,0,0,0.35);
        """
    else:
        vars_css = """
            --lf-bg: #d4dce8;
            --lf-card: #e8edf4;
            --lf-text: #1e293b;
            --lf-muted: #475569;
            --lf-border: #b8c5d6;
            --lf-navy: #0b1628;
            --lf-orange: #e85d04;
            --lf-orange-hover: #c2410c;
            --lf-blue: #2563eb;
            --lf-green: #15803d;
            --lf-amber: #d97706;
            --lf-red: #dc2626;
            --lf-sidebar: #0b1628;
            --lf-shadow: rgba(15, 23, 42, 0.12);
        """

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {{ {vars_css} }}

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
            font-size: 16px !important;
            color: var(--lf-text);
        }}

        #MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}

        .stApp {{
            background: var(--lf-bg) !important;
        }}

        .block-container {{
            padding: 1.25rem 1.5rem 3rem !important;
            max-width: 1200px !important;
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: var(--lf-sidebar) !important;
            border-right: none !important;
            box-shadow: 4px 0 24px var(--lf-shadow);
        }}
        section[data-testid="stSidebar"] * {{
            color: #e2e8f0 !important;
        }}
        section[data-testid="stSidebar"] .stRadio label,
        section[data-testid="stSidebar"] .stSelectbox label {{
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            padding: 0.65rem 0.5rem !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label {{
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 10px !important;
            margin-bottom: 0.35rem !important;
            padding: 0.6rem 0.75rem !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
            background: rgba(232,93,4,0.15) !important;
            border-color: var(--lf-orange) !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"],
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
            background: var(--lf-orange) !important;
            border-color: var(--lf-orange) !important;
            color: white !important;
        }}

        /* Buttons — large, obvious */
        .stButton > button {{
            min-height: 48px !important;
            font-size: 0.95rem !important;
            font-weight: 700 !important;
            border-radius: 10px !important;
            border: none !important;
            background: var(--lf-orange) !important;
            color: white !important;
            transition: transform 0.1s, opacity 0.1s;
        }}
        .stButton > button:hover {{
            background: var(--lf-orange-hover) !important;
            transform: translateY(-1px);
        }}
        .stButton > button[kind="secondary"] {{
            background: var(--lf-card) !important;
            color: var(--lf-text) !important;
            border: 2px solid var(--lf-border) !important;
        }}

        /* Forms & inputs */
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox > div > div {{
            min-height: 46px !important;
            font-size: 1rem !important;
            border-radius: 10px !important;
            border: 1px solid var(--lf-border) !important;
        }}
        div[data-testid="stForm"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 14px;
            padding: 1.25rem;
            box-shadow: 0 2px 8px var(--lf-shadow);
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab"] {{
            font-size: 1rem !important;
            font-weight: 700 !important;
            padding: 0.75rem 1.25rem !important;
        }}
        .stTabs [data-baseweb="tab"][aria-selected="true"] {{
            color: var(--lf-orange) !important;
            border-bottom: 3px solid var(--lf-orange) !important;
        }}

        /* Metrics */
        div[data-testid="stMetric"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 1px 4px var(--lf-shadow);
        }}
        div[data-testid="stMetric"] label {{
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            color: var(--lf-muted) !important;
        }}
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            font-size: 1.75rem !important;
            font-weight: 800 !important;
            color: var(--lf-text) !important;
        }}

        /* Brand blocks */
        .lf-sidebar-logo h1 {{
            font-size: 1.35rem !important;
            font-weight: 800 !important;
            color: #fff !important;
            margin: 0 !important;
            letter-spacing: -0.02em;
        }}
        .lf-sidebar-logo .accent {{ color: var(--lf-orange) !important; }}
        .lf-sidebar-tag {{
            font-size: 0.75rem;
            font-weight: 600;
            color: #94a3b8;
            margin-top: 0.15rem;
        }}
        .lf-trailer-chip {{
            background: rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 0.65rem 0.75rem;
            margin: 0.75rem 0;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .lf-trailer-chip .type {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #94a3b8;
        }}
        .lf-trailer-chip .spec {{
            font-size: 0.9rem;
            font-weight: 700;
            color: #f8fafc;
        }}
        .lp-mission {{
            font-size: 0.8rem;
            line-height: 1.5;
            color: #cbd5e1;
            padding: 0.5rem 0;
        }}
        .nav-group-label {{
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #64748b !important;
            margin: 0.75rem 0 0.35rem 0;
        }}

        /* Slim top bar */
        .lf-topbar {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 12px;
            padding: 0.85rem 1.25rem;
            margin-bottom: 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 4px var(--lf-shadow);
        }}
        .lf-topbar-brand {{
            font-size: 1.1rem;
            font-weight: 800;
            color: var(--lf-text);
        }}
        .lf-topbar-brand span {{ color: var(--lf-orange); }}
        .lf-topbar-sub {{
            font-size: 0.85rem;
            color: var(--lf-muted);
            margin-top: 0.1rem;
        }}
        .lf-topbar-right {{
            text-align: right;
            font-size: 0.8rem;
            color: var(--lf-muted);
        }}

        /* Page headers */
        .lf-page-title {{
            font-size: 1.75rem;
            font-weight: 800;
            color: var(--lf-text);
            margin-bottom: 0.25rem;
            letter-spacing: -0.02em;
        }}
        .lf-page-sub {{
            font-size: 1rem;
            color: var(--lf-muted);
            margin-bottom: 1.25rem;
        }}
        .lf-section-header {{
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--lf-text);
            margin: 1.5rem 0 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--lf-border);
        }}

        /* Lane banner — simple */
        .lf-lane-bar {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.75rem;
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-left: 4px solid var(--lf-orange);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1.25rem;
        }}
        .lf-lane-origin, .lf-lane-dest {{
            font-weight: 700;
            font-size: 1rem;
            color: var(--lf-text);
        }}
        .lf-lane-arrow {{ color: var(--lf-orange); font-size: 1.25rem; font-weight: 700; }}
        .lf-lane-meta {{
            margin-left: auto;
            text-align: right;
            font-size: 0.85rem;
            color: var(--lf-muted);
        }}
        .lf-lane-meta strong {{ color: var(--lf-green); font-size: 1rem; }}

        /* KPI grid */
        .lf-kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.75rem;
            margin-bottom: 1.25rem;
        }}
        @media (max-width: 900px) {{
            .lf-kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .lf-kpi {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 1px 4px var(--lf-shadow);
        }}
        .lf-kpi-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--lf-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .lf-kpi-value {{
            font-size: 1.5rem;
            font-weight: 800;
            color: var(--lf-text);
            margin-top: 0.25rem;
        }}
        .lf-kpi-delta {{ font-size: 0.75rem; color: var(--lf-green); margin-top: 0.15rem; }}

        /* Cards */
        .lf-load-card, .lf-lead-card, .lf-panel, .lf-call-log-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 12px;
            padding: 1rem 1.15rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 1px 3px var(--lf-shadow);
        }}
        .lf-load-card:hover, .lf-lead-card:hover {{
            border-color: var(--lf-orange);
        }}
        .lf-lead-card {{ border-left: 4px solid var(--lf-orange); }}
        .lf-load-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.35rem;
        }}
        .lf-load-bol {{ font-weight: 800; font-size: 1rem; color: var(--lf-text); }}
        .lf-load-revenue {{ font-weight: 800; font-size: 1.1rem; color: var(--lf-green); }}
        .lf-load-route {{ font-size: 0.9rem; color: var(--lf-muted); margin-bottom: 0.5rem; }}
        .lf-load-route strong {{ color: var(--lf-text); }}
        .lf-load-tags {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
        .lf-badge {{
            font-size: 0.72rem;
            font-weight: 600;
            padding: 0.2rem 0.55rem;
            border-radius: 6px;
            background: #d8e0ea;
            color: var(--lf-muted);
            border: 1px solid var(--lf-border);
        }}
        .lf-badge.commodity {{ background: #dbeafe; color: #1d4ed8; border-color: #93c5fd; }}
        .lf-badge.weight {{ background: #dcfce7; color: #15803d; border-color: #86efac; }}
        .lf-badge.status {{ background: #ffedd5; color: #c2410c; border-color: #fdba74; }}
        .lf-lead-name {{ font-weight: 700; font-size: 1rem; color: var(--lf-text); }}
        .lf-lead-phone {{ font-size: 1rem; margin: 0.25rem 0; }}
        .lf-lead-phone a {{ color: var(--lf-blue) !important; font-weight: 700; text-decoration: none; }}
        .lf-lead-meta {{ font-size: 0.85rem; color: var(--lf-muted); }}

        /* Quick actions */
        .lf-quick-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }}
        @media (max-width: 768px) {{
            .lf-quick-grid {{ grid-template-columns: 1fr; }}
            .stButton > button {{ min-height: 56px !important; font-size: 1.05rem !important; }}
        }}

        /* ROI hero — simplified */
        .lf-roi-hero {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        @media (max-width: 768px) {{ .lf-roi-hero {{ grid-template-columns: 1fr; }} }}
        .lf-roi-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }}
        .lf-roi-label {{ font-size: 0.75rem; font-weight: 600; color: var(--lf-muted); text-transform: uppercase; }}
        .lf-roi-value {{ font-size: 1.35rem; font-weight: 800; color: var(--lf-green); margin-top: 0.25rem; }}
        .lf-roi-hint {{ font-size: 0.75rem; color: var(--lf-muted); margin-top: 0.15rem; }}

        /* Misc */
        .lf-suggest-card {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-left: 4px solid var(--lf-amber);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }}
        .lf-suggest-card.critical {{ background: #fef2f2; border-color: #fecaca; border-left-color: var(--lf-red); }}
        .lf-suggest-card.high {{ background: #fff7ed; border-color: #fed7aa; border-left-color: var(--lf-orange); }}
        .lf-suggest-card.low {{ background: #f0fdf4; border-color: #bbf7d0; border-left-color: var(--lf-green); }}
        .lp-privacy {{
            font-size: 0.72rem;
            color: #64748b;
            line-height: 1.4;
            padding: 0.5rem 0;
        }}
        .lf-traffic {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.6rem;
            border-radius: 20px;
        }}
        .lf-traffic.green {{ background: #dcfce7; color: #166534; }}
        .lf-traffic.amber {{ background: #fef3c7; color: #92400e; }}
        .lf-traffic.red {{ background: #fee2e2; color: #991b1b; }}
        .lf-voice-panel {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-left: 4px solid var(--lf-blue);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        .lf-score-ring {{
            width: 80px; height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            font-weight: 800;
            border: 3px solid var(--lf-orange);
            margin: 0 auto;
        }}
        .lf-map-sim {{
            height: 120px;
            background: linear-gradient(90deg, #c5d0de, #dce3ed);
            border-radius: 12px;
            border: 1px solid var(--lf-border);
            position: relative;
            margin-bottom: 1rem;
        }}
        .lf-map-route {{
            position: absolute;
            top: 50%; left: 10%; right: 10%;
            height: 4px;
            background: var(--lf-orange);
            border-radius: 2px;
            transform: translateY(-50%);
        }}
        .lf-geo-card, .lf-bulk-stat {{ border-radius: 10px; }}
        h1, h2, h3 {{ color: var(--lf-text) !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )