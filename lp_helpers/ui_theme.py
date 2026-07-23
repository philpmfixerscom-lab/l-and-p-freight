"""Futuristic HUD UI theme for L & P Freight Platform.

Night mode = dispatch/cabin neon cyber HUD (high contrast).
Day mode = clean freight polish with brand orange accents.
"""

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
    """Apply high-contrast HUD stylesheet (neon night / clean day)."""
    if night_mode:
        vars_css = """
            --lf-bg: #050a12;
            --lf-card: #0c1524;
            --lf-text: #F8FAFC;
            --lf-muted: #94A8C4;
            --lf-border: #1e3a5f;
            --lf-navy: #050a12;
            --lf-orange: #FF6B00;
            --lf-orange-hover: #FF9500;
            --lf-blue: #22D3EE;
            --lf-cyan: #22D3EE;
            --lf-cyan-dim: rgba(34, 211, 238, 0.12);
            --lf-cyan-glow: rgba(34, 211, 238, 0.45);
            --lf-orange-glow: rgba(255, 107, 0, 0.55);
            --lf-green: #4ade80;
            --lf-amber: #fbbf24;
            --lf-red: #f87171;
            --lf-sidebar: #03060d;
            --lf-shadow: rgba(0, 0, 0, 0.55);
            --lf-hud-edge: rgba(34, 211, 238, 0.35);
        """
    else:
        vars_css = """
            --lf-bg: #f8fafc;
            --lf-card: #ffffff;
            --lf-text: #0f172a;
            --lf-muted: #475569;
            --lf-border: #cbd5e1;
            --lf-navy: #0b1628;
            --lf-orange: #e85d04;
            --lf-orange-hover: #c2410c;
            --lf-blue: #2563eb;
            --lf-cyan: #0891b2;
            --lf-cyan-dim: rgba(8, 145, 178, 0.08);
            --lf-cyan-glow: rgba(8, 145, 178, 0.2);
            --lf-orange-glow: rgba(232, 93, 4, 0.3);
            --lf-green: #15803d;
            --lf-amber: #d97706;
            --lf-red: #dc2626;
            --lf-sidebar: #e2e8f0;
            --lf-shadow: rgba(15, 23, 42, 0.12);
            --lf-hud-edge: rgba(232, 93, 4, 0.35);
        """

    night_bg = """
        .stApp {{
            background:
                radial-gradient(ellipse 120% 80% at 10% -10%, rgba(34, 211, 238, 0.14) 0%, transparent 50%),
                radial-gradient(ellipse 90% 60% at 100% 0%, rgba(255, 107, 0, 0.10) 0%, transparent 45%),
                radial-gradient(ellipse 70% 50% at 50% 100%, rgba(34, 211, 238, 0.06) 0%, transparent 50%),
                linear-gradient(165deg, #050a12 0%, #0a1220 45%, #0b1528 100%) !important;
        }}
    """ if night_mode else """
        .stApp {{
            background: var(--lf-bg) !important;
        }}
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

        {night_bg}

        .block-container {{
            padding: 1.25rem 1.5rem 3rem !important;
            max-width: 1200px !important;
        }}

        /* Sidebar — HUD rail */
        section[data-testid="stSidebar"] {{
            background:
                linear-gradient(180deg, rgba(34, 211, 238, 0.06) 0%, transparent 28%),
                var(--lf-sidebar) !important;
            border-right: 1px solid var(--lf-hud-edge) !important;
            box-shadow: 4px 0 32px var(--lf-shadow), inset -1px 0 0 rgba(34, 211, 238, 0.08);
        }}
        section[data-testid="stSidebar"] * {{
            color: var(--lf-text) !important;
        }}
        section[data-testid="stSidebar"] .stRadio label,
        section[data-testid="stSidebar"] .stSelectbox label {{
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            padding: 0.65rem 0.5rem !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label {{
            background: rgba(255,255,255,0.03) !important;
            border: 1px solid rgba(34, 211, 238, 0.12) !important;
            border-radius: 10px !important;
            margin-bottom: 0.35rem !important;
            padding: 0.6rem 0.75rem !important;
            transition: background 0.15s, border-color 0.15s, transform 0.1s, box-shadow 0.15s;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
            background: rgba(255, 107, 0, 0.12) !important;
            border-color: var(--lf-orange) !important;
            box-shadow: 0 0 12px rgba(255, 107, 0, 0.25);
            transform: translateX(2px);
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"],
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
            background: linear-gradient(90deg, #FF6B00, #FF9500) !important;
            border-color: var(--lf-orange) !important;
            color: #050a12 !important;
            font-weight: 700 !important;
            box-shadow: 0 0 18px var(--lf-orange-glow) !important;
        }}

        /* Buttons — large, glowing, freight-visible */
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
            width: 100% !important;
            min-height: 3.5rem !important;
            height: 3.5rem !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
            background: linear-gradient(90deg, #FF6B00, #FF9500) !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            box-shadow: 0 0 12px rgba(255, 107, 0, 0.45), 0 4px 18px rgba(255, 107, 0, 0.35) !important;
            transition: transform 0.1s, box-shadow 0.15s;
            text-shadow: 0 1px 0 rgba(0,0,0,0.2);
        }}
        .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 0 22px rgba(255, 107, 0, 0.7), 0 6px 24px rgba(255, 107, 0, 0.5) !important;
        }}
        .stButton > button:active, .stFormSubmitButton > button:active, .stDownloadButton > button:active {{
            transform: scale(0.98);
        }}
        .stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondary"] {{
            background: var(--lf-card) !important;
            color: var(--lf-text) !important;
            border: 1px solid var(--lf-hud-edge) !important;
            box-shadow: 0 0 8px rgba(34, 211, 238, 0.12) !important;
            text-shadow: none !important;
        }}
        .stButton > button[kind="secondary"]:hover, .stFormSubmitButton > button[kind="secondary"]:hover {{
            border-color: var(--lf-cyan) !important;
            box-shadow: 0 0 16px var(--lf-cyan-glow) !important;
        }}

        /* Forms & inputs — HUD frames */
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox > div > div {{
            min-height: 46px !important;
            font-size: 1rem !important;
            border-radius: 10px !important;
            border: 1px solid var(--lf-border) !important;
            transition: border-color 0.15s, box-shadow 0.15s;
        }}
        .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus,
        .stSelectbox > div > div:focus {{
            border-color: var(--lf-cyan) !important;
            box-shadow: 0 0 0 3px var(--lf-cyan-dim), 0 0 14px var(--lf-cyan-glow) !important;
        }}
        .stTextInput input:disabled, .stNumberInput input:disabled, .stTextArea textarea:disabled {{
            opacity: 0.6 !important;
            cursor: not-allowed !important;
            background: var(--lf-bg) !important;
        }}
        div[data-testid="stForm"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 14px;
            padding: 1.25rem;
            box-shadow: 0 0 24px var(--lf-cyan-dim), 0 8px 24px var(--lf-shadow);
        }}
        div[data-testid="stForm"] > div {{
            gap: 0.75rem !important;
        }}

        /* Validation / status messages */
        .stSuccess, div[data-testid="stSuccess"] {{
            border-left: 4px solid var(--lf-green) !important;
            border-radius: 10px !important;
            box-shadow: -2px 0 12px rgba(74, 222, 128, 0.25);
        }}
        .stError, div[data-testid="stError"] {{
            border-left: 4px solid var(--lf-red) !important;
            border-radius: 10px !important;
            box-shadow: -2px 0 12px rgba(248, 113, 113, 0.25);
        }}
        .stWarning, div[data-testid="stWarning"] {{
            border-left: 4px solid var(--lf-amber) !important;
            border-radius: 10px !important;
        }}
        .stInfo, div[data-testid="stInfo"] {{
            border-left: 4px solid var(--lf-blue) !important;
            border-radius: 10px !important;
            box-shadow: -2px 0 12px var(--lf-cyan-glow);
        }}

        /* Expanders — HUD panels */
        div[data-testid="stExpander"] {{
            border: 1px solid var(--lf-hud-edge) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
            margin-bottom: 0.75rem !important;
            background: var(--lf-card) !important;
            box-shadow: 0 0 16px rgba(34, 211, 238, 0.06);
        }}
        div[data-testid="stExpander"] details {{
            border: none !important;
        }}
        div[data-testid="stExpander"] summary {{
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            padding: 0.85rem 1rem !important;
            color: var(--lf-text) !important;
            transition: background 0.15s;
        }}
        div[data-testid="stExpander"] summary:hover {{
            background: var(--lf-cyan-dim) !important;
        }}

        /* Dividers */
        hr, .stDivider {{
            border: none !important;
            border-top: 1px solid var(--lf-border) !important;
            margin: 1.25rem 0 !important;
            box-shadow: 0 1px 0 rgba(34, 211, 238, 0.08);
        }}

        /* Smooth transitions for interactive elements */
        .stButton > button, .stDownloadButton > button {{
            transition: transform 0.1s, opacity 0.1s, background 0.15s, box-shadow 0.15s;
        }}
        .stButton > button:active {{
            transform: scale(0.98);
        }}

        /* Caption / helper text */
        .stCaption, div[data-testid="stCaption"] {{
            color: var(--lf-muted) !important;
            font-size: 0.85rem !important;
        }}

        /* Subheader */
        .stSubheader, div[data-testid="stSubheader"] {{
            color: var(--lf-text) !important;
            font-weight: 700 !important;
            font-size: 1.1rem !important;
            margin-bottom: 0.75rem !important;
        }}

        /* Tabs — neon underline */
        .stTabs [data-baseweb="tab"] {{
            font-size: 1rem !important;
            font-weight: 700 !important;
            padding: 0.75rem 1.25rem !important;
            border-radius: 10px 10px 0 0 !important;
            transition: background 0.15s, color 0.15s, box-shadow 0.15s;
        }}
        .stTabs [data-baseweb="tab"][aria-selected="true"] {{
            color: var(--lf-cyan) !important;
            border-bottom: 3px solid var(--lf-cyan) !important;
            background: var(--lf-cyan-dim) !important;
            box-shadow: 0 4px 16px rgba(34, 211, 238, 0.2);
            text-shadow: 0 0 12px var(--lf-cyan-glow);
        }}
        .stTabs [data-baseweb="tab"]:hover {{
            background: rgba(255, 107, 0, 0.08) !important;
            color: var(--lf-orange) !important;
        }}

        /* Metrics — HUD KPI tiles */
        div[data-testid="stMetric"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 0 20px var(--lf-cyan-dim), inset 0 1px 0 var(--lf-cyan-dim);
        }}
        div[data-testid="stMetric"] label {{
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            color: var(--lf-muted) !important;
            text-transform: uppercase !important;
            letter-spacing: 0.06em !important;
        }}
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            font-size: 1.75rem !important;
            font-weight: 800 !important;
            color: var(--lf-cyan) !important;
            text-shadow: 0 0 18px var(--lf-cyan-glow);
        }}

        /* Brand blocks */
        .lf-sidebar-logo h1 {{
            font-size: 1.35rem !important;
            font-weight: 800 !important;
            color: var(--lf-text) !important;
            margin: 0 !important;
            letter-spacing: -0.02em;
            text-shadow: 0 0 20px var(--lf-cyan-glow);
        }}
        .lf-sidebar-logo .accent {{
            color: var(--lf-orange) !important;
            text-shadow: 0 0 12px var(--lf-orange-glow);
        }}
        .lf-sidebar-tag {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--lf-muted);
            margin-top: 0.15rem;
        }}
        .lf-trailer-chip {{
            background: var(--lf-cyan-dim);
            border-radius: 10px;
            padding: 0.65rem 0.75rem;
            margin: 0.75rem 0;
            border: 1px solid var(--lf-hud-edge);
            box-shadow: 0 0 12px var(--lf-cyan-dim);
        }}
        .lf-trailer-chip .type {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--lf-muted);
        }}
        .lf-trailer-chip .spec {{
            font-size: 0.9rem;
            font-weight: 700;
            color: var(--lf-text);
        }}
        .lp-mission {{
            font-size: 0.8rem;
            line-height: 1.5;
            color: var(--lf-muted);
            padding: 0.5rem 0;
        }}
        .nav-group-label {{
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--lf-cyan) !important;
            margin: 0.75rem 0 0.35rem 0;
            text-shadow: 0 0 10px rgba(34, 211, 238, 0.3);
        }}

        /* Slim top bar — mission strip */
        .lf-topbar {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 0.85rem 1.25rem;
            margin-bottom: 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 0 24px var(--lf-cyan-dim), 0 4px 16px var(--lf-shadow);
        }}
        .lf-topbar-brand {{
            font-size: 1.1rem;
            font-weight: 800;
            color: var(--lf-text);
        }}
        .lf-topbar-brand span {{
            color: var(--lf-orange);
            text-shadow: 0 0 12px var(--lf-orange-glow);
        }}
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
            text-shadow: 0 0 24px rgba(34, 211, 238, 0.2);
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
            border-bottom: 2px solid var(--lf-hud-edge);
            display: flex;
            align-items: center;
            gap: 0.5rem;
            box-shadow: 0 2px 0 rgba(34, 211, 238, 0.08);
        }}

        /* Lane banner — HUD strip */
        .lf-lane-bar {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.75rem;
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-left: 4px solid var(--lf-orange);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 0 20px var(--lf-orange-glow);
        }}
        .lf-lane-origin, .lf-lane-dest {{
            font-weight: 700;
            font-size: 1rem;
            color: var(--lf-text);
        }}
        .lf-lane-arrow {{
            color: var(--lf-cyan);
            font-size: 1.25rem;
            font-weight: 700;
            text-shadow: 0 0 10px var(--lf-cyan-glow);
        }}
        .lf-lane-meta {{
            margin-left: auto;
            text-align: right;
            font-size: 0.85rem;
            color: var(--lf-muted);
        }}
        .lf-lane-meta strong {{
            color: var(--lf-green);
            font-size: 1rem;
            text-shadow: 0 0 10px rgba(74, 222, 128, 0.4);
        }}

        /* KPI grid — HUD tiles */
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
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 0 18px var(--lf-cyan-dim), inset 0 1px 0 var(--lf-cyan-dim);
            transition: transform 0.1s, box-shadow 0.15s, border-color 0.15s;
        }}
        .lf-kpi:hover {{
            transform: translateY(-2px);
            border-color: var(--lf-cyan);
            box-shadow: 0 0 28px var(--lf-cyan-glow);
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
            color: var(--lf-cyan);
            margin-top: 0.25rem;
            text-shadow: 0 0 16px var(--lf-cyan-glow);
        }}
        .lf-kpi-delta {{ font-size: 0.75rem; color: var(--lf-green); margin-top: 0.15rem; }}

        /* Cards — glass HUD panels */
        .lf-load-card, .lf-lead-card, .lf-panel, .lf-call-log-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 1rem 1.15rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 0 16px var(--lf-cyan-dim), 0 4px 12px var(--lf-shadow);
        }}
        .lf-load-card:hover, .lf-lead-card:hover {{
            border-color: var(--lf-orange);
            box-shadow: 0 0 22px rgba(255, 107, 0, 0.25);
        }}
        .lf-lead-card {{ border-left: 4px solid var(--lf-orange); }}
        .lf-load-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.35rem;
        }}
        .lf-load-bol {{ font-weight: 800; font-size: 1rem; color: var(--lf-text); }}
        .lf-load-revenue {{
            font-weight: 800;
            font-size: 1.1rem;
            color: var(--lf-green);
            text-shadow: 0 0 10px rgba(74, 222, 128, 0.35);
        }}
        .lf-load-route {{ font-size: 0.9rem; color: var(--lf-muted); margin-bottom: 0.5rem; }}
        .lf-load-route strong {{ color: var(--lf-text); }}
        .lf-load-tags {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
        .lf-badge {{
            font-size: 0.72rem;
            font-weight: 600;
            padding: 0.2rem 0.55rem;
            border-radius: 6px;
            background: rgba(255,255,255,0.06);
            color: var(--lf-muted);
            border: 1px solid var(--lf-border);
            display: inline-block;
        }}
        .lf-badge.commodity {{ background: rgba(34, 211, 238, 0.12); color: var(--lf-cyan); border-color: rgba(34, 211, 238, 0.35); }}
        .lf-badge.weight {{ background: rgba(34,197,94,0.12); color: var(--lf-green); border-color: rgba(34,197,94,0.25); }}
        .lf-badge.status {{ background: rgba(255, 107, 0, 0.12); color: var(--lf-orange); border-color: rgba(255, 107, 0, 0.35); }}
        .lf-lead-name {{ font-weight: 700; font-size: 1rem; color: var(--lf-text); }}
        .lf-lead-phone {{ font-size: 1rem; margin: 0.25rem 0; }}
        .lf-lead-phone a {{
            color: var(--lf-cyan) !important;
            font-weight: 700;
            text-decoration: none;
            text-shadow: 0 0 8px var(--lf-cyan-glow);
        }}
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

        /* ROI hero — HUD */
        .lf-roi-hero {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        @media (max-width: 768px) {{ .lf-roi-hero {{ grid-template-columns: 1fr; }} }}
        .lf-roi-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
            box-shadow: 0 0 16px var(--lf-cyan-dim);
        }}
        .lf-roi-label {{ font-size: 0.75rem; font-weight: 600; color: var(--lf-muted); text-transform: uppercase; }}
        .lf-roi-value {{
            font-size: 1.35rem;
            font-weight: 800;
            color: var(--lf-green);
            margin-top: 0.25rem;
            text-shadow: 0 0 12px rgba(74, 222, 128, 0.4);
        }}
        .lf-roi-hint {{ font-size: 0.75rem; color: var(--lf-muted); margin-top: 0.15rem; }}

        /* Misc */
        .lf-suggest-card {{
            background: rgba(251,191,36,0.08);
            border: 1px solid rgba(251,191,36,0.25);
            border-left: 4px solid var(--lf-amber);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            color: var(--lf-text);
        }}
        .lf-suggest-card.critical {{ background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.25); border-left-color: var(--lf-red); }}
        .lf-suggest-card.high {{ background: rgba(232,93,4,0.08); border-color: rgba(232,93,4,0.25); border-left-color: var(--lf-orange); }}
        .lf-suggest-card.low {{ background: rgba(74,222,128,0.08); border-color: rgba(74,222,128,0.25); border-left-color: var(--lf-green); }}
        .lp-privacy {{
            font-size: 0.72rem;
            color: var(--lf-muted);
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
        .lf-traffic.green {{ background: rgba(34,197,94,0.15); color: var(--lf-green); }}
        .lf-traffic.amber {{ background: rgba(245,158,11,0.15); color: var(--lf-amber); }}
        .lf-traffic.red {{ background: rgba(239,68,68,0.15); color: var(--lf-red); }}
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
            background:
                radial-gradient(circle at 20% 50%, var(--lf-cyan-dim), transparent 40%),
                radial-gradient(circle at 80% 50%, rgba(255, 107, 0, 0.1), transparent 40%),
                linear-gradient(90deg, var(--lf-border), var(--lf-card));
            border-radius: 12px;
            border: 1px solid var(--lf-hud-edge);
            position: relative;
            margin-bottom: 1rem;
            box-shadow: inset 0 0 30px var(--lf-cyan-dim);
        }}
        .lf-map-route {{
            position: absolute;
            top: 50%; left: 10%; right: 10%;
            height: 4px;
            background: linear-gradient(90deg, var(--lf-orange), var(--lf-cyan));
            border-radius: 2px;
            transform: translateY(-50%);
            box-shadow: 0 0 12px var(--lf-cyan-glow);
        }}
        .lf-geo-card, .lf-bulk-stat {{ border-radius: 10px; }}
        h1, h2, h3 {{ color: var(--lf-text) !important; }}

        /* Dataframes / tables — high-contrast dispatch grid */
        div[data-testid="stDataFrame"] {{
            border: 1px solid var(--lf-hud-edge) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
            box-shadow: 0 0 20px rgba(34, 211, 238, 0.08) !important;
        }}
        div[data-testid="stDataFrame"] table {{
            border-collapse: collapse !important;
            width: 100% !important;
        }}
        div[data-testid="stDataFrame"] table thead th {{
            background: var(--lf-card) !important;
            color: var(--lf-cyan) !important;
            font-weight: 700 !important;
            font-size: 0.85rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.04em !important;
            padding: 0.75rem 0.85rem !important;
            border-bottom: 2px solid var(--lf-cyan) !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 1 !important;
            text-shadow: 0 0 10px var(--lf-cyan-glow);
        }}
        div[data-testid="stDataFrame"] table tbody tr:nth-child(odd) {{
            background: var(--lf-cyan-dim) !important;
        }}
        div[data-testid="stDataFrame"] table tbody tr:hover {{
            background: rgba(255, 107, 0, 0.1) !important;
        }}
        div[data-testid="stDataFrame"] table tbody td {{
            padding: 0.65rem 0.85rem !important;
            font-size: 0.95rem !important;
            color: var(--lf-text) !important;
            border-bottom: 1px solid var(--lf-border) !important;
            font-weight: 500 !important;
        }}

        /* Focus indicators — cyan ring for cabin visibility */
        .stButton > button:focus-visible,
        .stTextInput input:focus-visible,
        .stNumberInput input:focus-visible,
        .stTextArea textarea:focus-visible,
        .stSelectbox > div > div:focus-visible {{
            outline: 2px solid var(--lf-cyan) !important;
            outline-offset: 2px !important;
            box-shadow: 0 0 12px var(--lf-cyan-glow) !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:focus-visible {{
            outline: 2px solid var(--lf-orange) !important;
            outline-offset: 2px !important;
        }}

        /* Empty states */
        .lf-empty-state {{
            text-align: center;
            padding: 2.5rem 1.5rem;
            color: var(--lf-muted);
            border: 2px dashed var(--lf-border);
            border-radius: 14px;
            margin: 1rem 0;
        }}
        .lf-empty-state-icon {{
            font-size: 2.5rem;
            margin-bottom: 0.75rem;
            display: block;
        }}
        .lf-empty-state-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--lf-text);
            margin-bottom: 0.35rem;
        }}
        .lf-empty-state-body {{
            font-size: 0.9rem;
            max-width: 32ch;
            margin: 0 auto;
            line-height: 1.5;
        }}

        /* Card hover polish */
        .lf-load-card, .lf-lead-card, .lf-panel, .lf-call-log-card {{
            transition: border-color 0.15s, transform 0.1s, box-shadow 0.15s;
        }}
        .lf-load-card:hover, .lf-lead-card:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--lf-shadow);
        }}

        /* Suggestion card theme tokens */
        .lf-suggest-card {{
            background: rgba(251,191,36,0.08);
            border: 1px solid rgba(251,191,36,0.25);
            border-left: 4px solid var(--lf-amber);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            color: var(--lf-text);
        }}
        .lf-suggest-card.critical {{ background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.25); border-left-color: var(--lf-red); }}
        .lf-suggest-card.high {{ background: rgba(232,93,4,0.08); border-color: rgba(232,93,4,0.25); border-left-color: var(--lf-orange); }}
        .lf-suggest-card.low {{ background: rgba(74,222,128,0.08); border-color: rgba(74,222,128,0.25); border-left-color: var(--lf-green); }}

        /* Privacy banner */
        .lp-privacy {{
            font-size: 0.72rem;
            color: var(--lf-muted);
            line-height: 1.4;
            padding: 0.5rem 0;
        }}

        /* ---- Opportunity Desk (HUD cards) ---- */
        .lf-desk-hero {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 14px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
            box-shadow: 0 0 24px var(--lf-cyan-dim), 0 4px 16px var(--lf-shadow);
        }}
        .lf-desk-hero h2 {{
            margin: 0 0 0.25rem 0 !important;
            font-size: 1.55rem !important;
            font-weight: 800 !important;
            color: var(--lf-text) !important;
            text-shadow: 0 0 20px var(--lf-cyan-glow);
        }}
        .lf-desk-hero .sub {{
            color: var(--lf-muted);
            font-size: 0.95rem;
            margin: 0;
        }}
        .lf-desk-kpis {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.6rem;
            margin: 0.85rem 0 0.25rem;
        }}
        @media (max-width: 900px) {{
            .lf-desk-kpis {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .lf-desk-kpi {{
            background: var(--lf-cyan-dim);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
        }}
        .lf-desk-kpi .lbl {{
            font-size: 0.68rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--lf-muted);
        }}
        .lf-desk-kpi .val {{
            font-size: 1.05rem;
            font-weight: 800;
            color: var(--lf-cyan);
            text-shadow: 0 0 12px var(--lf-cyan-glow);
            margin-top: 0.15rem;
        }}
        .lf-opp-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-hud-edge);
            border-radius: 12px;
            padding: 0.9rem 1.05rem;
            margin-bottom: 0.35rem;
            box-shadow: 0 0 16px var(--lf-cyan-dim), 0 4px 12px var(--lf-shadow);
            transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
        }}
        .lf-opp-card:hover {{
            border-color: var(--lf-orange);
            box-shadow: 0 0 22px var(--lf-orange-glow);
            transform: translateY(-1px);
        }}
        .lf-opp-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.4rem;
        }}
        .lf-source-pill {{
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            border: 1px solid var(--lf-border);
            color: var(--lf-muted);
            background: rgba(255,255,255,0.04);
        }}
        .lf-source-pill.callin {{
            color: var(--lf-orange);
            border-color: rgba(255, 107, 0, 0.45);
            background: rgba(255, 107, 0, 0.12);
            box-shadow: 0 0 10px var(--lf-orange-glow);
        }}
        .lf-source-pill.repeat {{
            color: var(--lf-green);
            border-color: rgba(74, 222, 128, 0.4);
            background: rgba(74, 222, 128, 0.1);
        }}
        .lf-source-pill.paste {{
            color: var(--lf-amber);
            border-color: rgba(251, 191, 36, 0.4);
            background: rgba(251, 191, 36, 0.1);
        }}
        .lf-source-pill.lead {{
            color: var(--lf-cyan);
            border-color: rgba(34, 211, 238, 0.4);
            background: var(--lf-cyan-dim);
        }}
        .lf-source-pill.seed {{
            color: var(--lf-muted);
            border-color: var(--lf-border);
        }}
        .lf-source-pill.live {{
            color: var(--lf-cyan);
            border-color: var(--lf-cyan);
            background: var(--lf-cyan-dim);
            box-shadow: 0 0 12px var(--lf-cyan-glow);
        }}
        .lf-source-pill.manual {{
            color: var(--lf-text);
            border-color: var(--lf-border);
        }}
        .lf-opp-grade {{
            font-size: 0.85rem;
            font-weight: 800;
            color: var(--lf-cyan);
            text-shadow: 0 0 10px var(--lf-cyan-glow);
            white-space: nowrap;
        }}
        .lf-opp-lane {{
            font-size: 1.08rem;
            font-weight: 800;
            color: var(--lf-text);
            margin-bottom: 0.35rem;
            letter-spacing: -0.01em;
        }}
        .lf-opp-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem 0.85rem;
            align-items: baseline;
            margin-bottom: 0.3rem;
        }}
        .lf-opp-commodity {{
            font-weight: 700;
            color: var(--lf-text);
        }}
        .lf-opp-rate {{
            font-weight: 800;
            color: var(--lf-orange);
            text-shadow: 0 0 10px var(--lf-orange-glow);
        }}
        .lf-opp-net {{
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--lf-green);
        }}
        .lf-opp-contact {{
            font-size: 0.9rem;
            color: var(--lf-cyan);
            margin-top: 0.15rem;
        }}
        .lf-opp-notes {{
            font-size: 0.82rem;
            color: var(--lf-muted);
            margin-top: 0.25rem;
            line-height: 1.4;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_platform_theme(night_mode: bool | None = None) -> None:
    """
    Complete consistent theming for both Day and Night mode.
    Strong text visibility in form fields and emergency buttons.
    """
    if night_mode is None:
        if "night_mode" not in st.session_state:
            st.session_state.night_mode = True
        night = bool(st.session_state.night_mode)
    else:
        night = bool(night_mode)
        st.session_state.night_mode = night

    if night:
        # ====================== NIGHT MODE — neon cyber HUD ======================
        st.markdown(
            """
        <style>
        .stApp, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(ellipse 120% 80% at 10% -10%, rgba(34, 211, 238, 0.14) 0%, transparent 50%),
                radial-gradient(ellipse 90% 60% at 100% 0%, rgba(255, 107, 0, 0.10) 0%, transparent 45%),
                linear-gradient(165deg, #050a12 0%, #0a1220 45%, #0b1528 100%) !important;
            color: #F8FAFC !important;
        }
        .main, .block-container {
            background: transparent !important;
            color: #F8FAFC !important;
        }
        .stSidebar,
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebarContent"] {
            background:
                linear-gradient(180deg, rgba(34, 211, 238, 0.06) 0%, transparent 28%),
                #03060d !important;
            border-right: 1px solid rgba(34, 211, 238, 0.35) !important;
        }
        section[data-testid="stSidebar"] * {
            color: #F8FAFC !important;
        }

        h1, h2, h3, h4, h5, h6, p, label, span, .stMarkdown, .stMarkdown p {
            color: #F8FAFC !important;
        }

        /* Form Fields - High Visibility HUD */
        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        .stSelectbox > div > div,
        .stMultiSelect > div > div,
        [data-baseweb="select"] > div {
            background-color: #0c1524 !important;
            color: #e0e7ff !important;
            border: 1px solid #1e3a5f !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            -webkit-text-fill-color: #e0e7ff !important;
            caret-color: #22D3EE !important;
        }

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: #64748b !important;
            -webkit-text-fill-color: #64748b !important;
            opacity: 1 !important;
        }

        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stNumberInput input:focus {
            border-color: #22D3EE !important;
            box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.2), 0 0 16px rgba(34, 211, 238, 0.35) !important;
        }

        /* Select / dropdown menus */
        .stSelectbox span,
        .stSelectbox div[data-baseweb="select"] *,
        .stMultiSelect span,
        div[data-baseweb="popover"] li,
        ul[role="listbox"] li,
        [data-baseweb="select"] span {
            color: #e0e7ff !important;
            background-color: #0c1524 !important;
            -webkit-text-fill-color: #e0e7ff !important;
        }

        /* Primary Buttons — orange neon glow */
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {
            width: 100% !important;
            min-height: 3.5rem !important;
            height: 3.5rem !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
            background: linear-gradient(90deg, #FF6B00, #FF9500) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 12px !important;
            box-shadow: 0 0 14px rgba(255, 107, 0, 0.5), 0 4px 18px rgba(255, 107, 0, 0.35) !important;
            transition: transform 0.1s, box-shadow 0.15s;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 0 24px rgba(255, 107, 0, 0.75), 0 6px 24px rgba(255, 107, 0, 0.5) !important;
        }
        .stButton > button:active,
        .stDownloadButton > button:active,
        .stFormSubmitButton > button:active {
            transform: scale(0.98);
        }

        /* Secondary / cyan outline */
        button[kind="secondary"],
        .stButton > button[kind="secondary"],
        .stFormSubmitButton > button[kind="secondary"] {
            background-color: #0c1524 !important;
            color: #F8FAFC !important;
            border: 1px solid rgba(34, 211, 238, 0.4) !important;
            box-shadow: 0 0 8px rgba(34, 211, 238, 0.15) !important;
        }
        button[kind="secondary"]:hover,
        .stButton > button[kind="secondary"]:hover,
        .stFormSubmitButton > button[kind="secondary"]:hover {
            border-color: #22D3EE !important;
            box-shadow: 0 0 16px rgba(34, 211, 238, 0.4) !important;
        }

        /* Metrics — cyan glow values */
        div[data-testid="stMetric"] {
            background: linear-gradient(160deg, rgba(14, 28, 48, 0.95), rgba(8, 16, 30, 0.98)) !important;
            border: 1px solid rgba(34, 211, 238, 0.35) !important;
            border-radius: 12px !important;
            box-shadow: 0 0 20px rgba(34, 211, 238, 0.1), inset 0 1px 0 rgba(34, 211, 238, 0.12) !important;
        }
        div[data-testid="stMetric"] label {
            color: #94A8C4 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #22D3EE !important;
            font-size: 1.6rem !important;
            font-weight: 800 !important;
            text-shadow: 0 0 18px rgba(34, 211, 238, 0.45) !important;
        }

        /* Nav pills */
        div[data-testid="stHorizontalBlock"] div[role="radiogroup"] label,
        div[data-testid="stHorizontalBlock"] .stButton > button[kind="secondary"] {
            color: #F8FAFC !important;
        }

        /* Tabs neon */
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            color: #22D3EE !important;
            border-bottom: 3px solid #22D3EE !important;
            text-shadow: 0 0 12px rgba(34, 211, 238, 0.4);
        }
        </style>
            """,
            unsafe_allow_html=True,
        )

    else:
        # ====================== DAY MODE ======================
        st.markdown(
            """
            <style>
            .stApp, [data-testid="stAppViewContainer"], .main, .block-container {
                background-color: #f8fafc !important;
                color: #0f172a !important;
            }
            .stSidebar,
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebarContent"] {
                background-color: #e2e8f0 !important;
            }
            section[data-testid="stSidebar"] * {
                color: #0f172a !important;
            }

            h1, h2, h3, h4, h5, h6, p, label, span, .stMarkdown, .stMarkdown p {
                color: #0f172a !important;
            }

            /* Form Fields - High Visibility */
            .stTextInput input,
            .stTextArea textarea,
            .stNumberInput input,
            .stSelectbox > div > div,
            .stMultiSelect > div > div,
            [data-baseweb="select"] > div {
                background-color: #ffffff !important;
                color: #0f172a !important;
                border: 2px solid #cbd5e1 !important;
                font-size: 1.05rem !important;
                border-radius: 8px !important;
                -webkit-text-fill-color: #0f172a !important;
                caret-color: #0f172a !important;
            }

            .stTextInput input::placeholder,
            .stTextArea textarea::placeholder {
                color: #64748b !important;
                -webkit-text-fill-color: #64748b !important;
                opacity: 1 !important;
            }

            .stTextInput input:focus,
            .stTextArea textarea:focus,
            .stNumberInput input:focus {
                border-color: #22D3EE !important;
                box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.2) !important;
            }

            .stSelectbox span,
            .stSelectbox div[data-baseweb="select"] *,
            .stMultiSelect span,
            div[data-baseweb="popover"] li,
            ul[role="listbox"] li,
            [data-baseweb="select"] span {
                color: #0f172a !important;
                background-color: #ffffff !important;
                -webkit-text-fill-color: #0f172a !important;
            }

            /* Buttons */
            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                width: 100% !important;
                min-height: 3.5rem !important;
                height: 3.5rem !important;
                font-size: 1.2rem !important;
                font-weight: 700 !important;
                background: linear-gradient(90deg, #FF6B00, #FF9500) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 12px !important;
                box-shadow: 0 4px 15px rgba(255, 107, 0, 0.35) !important;
                transition: transform 0.1s, box-shadow 0.15s;
            }
            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(255, 107, 0, 0.5) !important;
            }
            .stButton > button:active,
            .stDownloadButton > button:active,
            .stFormSubmitButton > button:active {
                transform: scale(0.98);
            }

            /* Emergency / secondary buttons - Strong Contrast */
            button[kind="secondary"],
            .stButton > button[kind="secondary"],
            .stFormSubmitButton > button[kind="secondary"] {
                background-color: #f1f5f9 !important;
                color: #0f172a !important;
                border: 2px solid #cbd5e1 !important;
            }
            button[kind="secondary"]:hover,
            .stButton > button[kind="secondary"]:hover {
                border-color: #FF6B00 !important;
                box-shadow: 0 2px 8px rgba(255, 107, 0, 0.2) !important;
            }

            /* Metrics */
            div[data-testid="stMetric"] {
                background-color: #ffffff !important;
                border: 2px solid #cbd5e1 !important;
                border-radius: 10px !important;
            }
            div[data-testid="stMetric"] label {
                color: #475569 !important;
            }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {
                color: #FF6B00 !important;
                font-size: 1.6rem !important;
                font-weight: 800 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

