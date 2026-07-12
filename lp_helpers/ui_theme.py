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


# The real, working screens of the app (label, session key, icon)
SCREENS: list[tuple[str, str, str]] = [
    ("Dashboard", "Dashboard", "📊"),
    ("Leads", "Leads", "📇"),
    ("Log Load", "Log Load", "🚚"),
    ("Rate", "Rate Calculator", "🧮"),
    ("Pay", "Billing & Pay", "💰"),
    ("BOL", "BOL", "📄"),
    ("Portal", "Portal", "🏢"),
    ("Maps", "Maps", "🗺️"),
    ("Alerts", "Notifications", "🔔"),
    ("Search", "Search", "🔍"),
    ("Analytics", "Analytics", "📉"),
    ("Documents", "Documents", "📁"),
    ("Compliance", "Compliance", "✅"),
    ("Booking", "Booking", "📋"),
]


def inject_mobile_css() -> None:
    """Mobile-first native-app theme — phone-width column, elevated cards,
    bottom navigation, status pills, skeletons and polished inputs."""
    light_css = """
        --lf-bg: #eef2f7;
        --lf-card: #ffffff;
        --lf-text: #0f172a;
        --lf-muted: #64748b;
        --lf-border: #e2e8f0;
        --lf-navy: #0b1628;
        --lf-orange: #ea580c;
        --lf-orange-hover: #c2410c;
        --lf-blue: #2563eb;
        --lf-green: #16a34a;
        --lf-amber: #d97706;
        --lf-red: #dc2626;
        --lf-shadow: rgba(15, 23, 42, 0.08);
        --lf-nav: rgba(255, 255, 255, 0.92);
    """
    dark_css = """
        --lf-bg: #0b1120;
        --lf-card: #131c2e;
        --lf-text: #f1f5f9;
        --lf-muted: #94a3b8;
        --lf-border: #243049;
        --lf-navy: #0b1628;
        --lf-orange: #fb923c;
        --lf-orange-hover: #f97316;
        --lf-blue: #60a5fa;
        --lf-green: #4ade80;
        --lf-amber: #fbbf24;
        --lf-red: #f87171;
        --lf-shadow: rgba(0, 0, 0, 0.4);
        --lf-nav: rgba(19, 28, 46, 0.92);
    """

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {{ {light_css} }}
        @media (prefers-color-scheme: dark) {{ :root {{ {dark_css} }} }}

        html, body, [class*="css"], .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            font-size: 16px !important;
            color: var(--lf-text);
            -webkit-font-smoothing: antialiased;
        }}

        #MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
        .stApp {{ background: var(--lf-bg) !important; min-height: 100vh; }}

        /* Phone-width column, like a native app */
        .block-container {{
            max-width: 600px !important;
            padding: 0.75rem 0.9rem calc(96px + env(safe-area-inset-bottom)) !important;
            margin: 0 auto !important;
        }}
        .main .block-container {{ padding-top: 0.75rem !important; }}

        /* Top progress shimmer (perceived speed) */
        .stApp::before {{
            content: "";
            position: sticky;
            top: 0;
            display: block;
            height: 3px;
            background: linear-gradient(90deg, transparent, var(--lf-orange), transparent);
            background-size: 200% 100%;
            animation: lf-shimmer 2.4s linear infinite;
            z-index: 999;
        }}
        @keyframes lf-shimmer {{ 0% {{ background-position: 200% 0; }} 100% {{ background-position: -200% 0; }} }}

        /* Smooth, alive feel */
        * {{ transition: background-color 0.15s ease, border-color 0.15s ease; }}

        /* Buttons — large, obvious touch targets */
        .stButton > button {{
            min-height: 52px !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            border-radius: 14px !important;
            border: none !important;
            background: linear-gradient(180deg, #f97316, var(--lf-orange)) !important;
            color: #fff !important;
            box-shadow: 0 4px 12px rgba(234, 88, 12, 0.28);
            transition: transform 0.08s ease, filter 0.15s ease;
            width: 100% !important;
        }}
        .stButton > button:hover {{ filter: brightness(1.05); transform: translateY(-1px); }}
        .stButton > button:active {{ transform: scale(0.985); }}
        .stButton > button[kind="secondary"] {{
            background: var(--lf-card) !important;
            color: var(--lf-text) !important;
            border: 1.5px solid var(--lf-border) !important;
            box-shadow: none !important;
        }}

        /* Forms & inputs — comfy, rounded */
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox > div > div, .stDateInput input {{
            min-height: 50px !important;
            font-size: 1rem !important;
            border-radius: 12px !important;
            border: 1.5px solid var(--lf-border) !important;
            background: var(--lf-card) !important;
            color: var(--lf-text) !important;
        }}
        div[data-testid="stForm"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 18px;
            padding: 1.1rem 1rem 1.25rem;
            box-shadow: 0 6px 20px var(--lf-shadow);
        }}
        .stSlider [data-testid="stThumbValue"] {{ font-weight: 700; }}

        /* Metrics as elevated cards */
        div[data-testid="stMetric"] {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 16px;
            padding: 0.9rem 1rem;
            box-shadow: 0 4px 14px var(--lf-shadow);
            transition: transform 0.12s ease, box-shadow 0.12s ease;
        }}
        div[data-testid="stMetric"]:hover {{ transform: translateY(-2px); }}
        div[data-testid="stMetric"] label {{
            font-size: 0.78rem !important; font-weight: 600; color: var(--lf-muted) !important;
            letter-spacing: 0.02em;
        }}
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            font-size: 1.7rem !important; font-weight: 800; color: var(--lf-text) !important;
        }}

        /* DataFrames -> mobile cards */
        .stDataFrame {{ border-radius: 14px; overflow: hidden; border: 1px solid var(--lf-border); }}

        /* Smooth scrolling */
        .stApp, .main, .block-container {{ scroll-behavior: smooth; }}

        /* ============ Bottom navigation (mobile-first) ============ */
        .lf-navbar {{
            position: fixed;
            left: 0; right: 0; bottom: 0;
            z-index: 900;
            display: flex;
            justify-content: space-around;
            align-items: stretch;
            gap: 2px;
            padding: 6px 4px calc(6px + env(safe-area-inset-bottom));
            background: var(--lf-nav);
            backdrop-filter: saturate(180%) blur(16px);
            -webkit-backdrop-filter: saturate(180%) blur(16px);
            border-top: 1px solid var(--lf-border);
            box-shadow: 0 -4px 18px rgba(15, 23, 42, 0.12);
        }}
        .lf-nav-item {{ flex: 1 1 0; min-width: 0; }}
        .lf-nav-item button {{
            width: 100% !important;
            min-height: 56px !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: var(--lf-muted) !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            line-height: 1.1 !important;
            border-radius: 12px !important;
            padding: 4px 2px !important;
            display: flex !important;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            transition: transform 0.08s ease, background-color 0.15s ease;
        }}
        .lf-nav-item button:active {{ transform: scale(0.92); background: rgba(234,88,12,0.08) !important; }}
        .lf-nav-item .lf-nav-ico {{ font-size: 21px !important; line-height: 1; }}
        .lf-nav-item.lf-nav-active button {{
            color: var(--lf-orange) !important;
            background: rgba(234, 88, 12, 0.10) !important;
        }}
        .lf-nav-item {{ flex: 1 1 0; min-width: 0; }}
        .lf-nav-item button {{
            width: 100% !important;
            min-height: 56px !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: var(--lf-muted) !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            line-height: 1.1 !important;
            border-radius: 12px !important;
            padding: 4px 2px !important;
            display: flex !important;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            transition: transform 0.08s ease, background-color 0.15s ease;
        }}
        .lf-nav-item button:active {{ transform: scale(0.92); background: rgba(234,88,12,0.08) !important; }}
        .lf-nav-item .lf-nav-ico {{ font-size: 21px !important; line-height: 1; }}
        .lf-nav-item.lf-nav-active button {{
            color: var(--lf-orange) !important;
            background: rgba(234, 88, 12, 0.10) !important;
        }}

        /* ============ Cards & lists ============ */
        .lf-card, .lf-panel, .lf-load-card, .lf-lead-card, .lf-call-log-card {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.7rem;
            box-shadow: 0 4px 14px var(--lf-shadow);
            transition: transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease;
        }}
        .lf-card:hover, .lf-lead-card:hover {{ transform: translateY(-2px); border-color: var(--lf-orange); }}
        .lf-lead-card {{ border-left: 4px solid var(--lf-orange); }}
        .lf-section {{ margin: 1.4rem 0 0.6rem; font-size: 1.05rem; font-weight: 700; color: var(--lf-text); }}
        .lf-row {{ display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }}
        .lf-muted {{ color: var(--lf-muted); font-size: 0.85rem; }}

        /* Status pills */
        .lf-pill {{
            display: inline-flex; align-items: center; gap: 0.3rem;
            font-size: 0.72rem; font-weight: 700; padding: 0.22rem 0.6rem;
            border-radius: 999px; border: 1px solid var(--lf-border);
            background: #f1f5f9; color: var(--lf-muted); white-space: nowrap;
        }}
        .lf-pill.green {{ background: #dcfce7; color: #15803d; border-color: #bbf7d0; }}
        .lf-pill.amber {{ background: #fef3c7; color: #b45309; border-color: #fde68a; }}
        .lf-pill.red {{ background: #fee2e2; color: #b91c1c; border-color: #fecaca; }}
        .lf-pill.blue {{ background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }}
        .lf-pill.orange {{ background: #ffedd5; color: #c2410c; border-color: #fed7aa; }}
        .lf-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: currentColor; }}

        /* Top bar */
        .lf-topbar {{
            background: var(--lf-card);
            border: 1px solid var(--lf-border);
            border-radius: 16px;
            padding: 0.8rem 1.1rem;
            margin-bottom: 1rem;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 4px 14px var(--lf-shadow);
        }}
        .lf-topbar-brand {{ font-size: 1.15rem; font-weight: 800; color: var(--lf-text); letter-spacing: -0.02em; }}
        .lf-topbar-brand span {{ color: var(--lf-orange); }}
        .lf-topbar-sub {{ font-size: 0.8rem; color: var(--lf-muted); margin-top: 0.1rem; }}
        .lf-topbar-right {{ text-align: right; font-size: 0.8rem; color: var(--lf-muted); }}

        .lf-page-title {{ font-size: 1.6rem; font-weight: 800; color: var(--lf-text); margin-bottom: 0.1rem; letter-spacing: -0.02em; }}
        .lf-trailer-chip {{
            background: var(--lf-card); border: 1px solid var(--lf-border); border-left: 4px solid var(--lf-orange);
            border-radius: 14px; padding: 0.7rem 0.9rem; margin: 0.85rem 0;
            box-shadow: 0 4px 14px var(--lf-shadow);
        }}
        .lf-trailer-chip .type {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--lf-muted); }}
        .lf-trailer-chip .spec {{ font-size: 0.95rem; font-weight: 700; color: var(--lf-text); }}
        .lf-trailer-sub {{ font-size: 0.8rem; color: var(--lf-muted); margin-top: 0.1rem; }}

        .lf-suggest-card {{
            background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid var(--lf-amber);
            border-radius: 14px; padding: 0.8rem 1rem; margin-bottom: 0.5rem; font-size: 0.9rem;
        }}
        .lf-suggest-card.critical {{ background: #fef2f2; border-color: #fecaca; border-left-color: var(--lf-red); }}
        .lf-suggest-card.high {{ background: #fff7ed; border-color: #fed7aa; border-left-color: var(--lf-orange); }}
        .lf-suggest-card.low {{ background: #f0fdf4; border-color: #bbf7d0; border-left-color: var(--lf-green); }}

        .lf-empty {{
            text-align: center; padding: 2.2rem 1rem; background: var(--lf-card);
            border: 1px dashed var(--lf-border); border-radius: 18px; margin: 1rem 0;
        }}
        .lf-empty .lf-empty-ico {{ font-size: 2.6rem; }}
        .lf-empty .lf-empty-title {{ font-weight: 700; font-size: 1.05rem; margin: 0.6rem 0 0.2rem; color: var(--lf-text); }}
        .lf-empty .lf-empty-sub {{ color: var(--lf-muted); font-size: 0.9rem; }}

        .lf-skeleton {{
            background: linear-gradient(90deg, #e9eef5 25%, #f4f7fb 37%, #e9eef5 63%);
            background-size: 400% 100%;
            animation: lf-skel 1.4s ease infinite;
            border-radius: 12px; margin-bottom: 0.6rem;
        }}
        @keyframes lf-skel {{ 0% {{ background-position: 100% 0; }} 100% {{ background-position: -100% 0; }} }}

        .lf-badge {{
            font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.55rem; border-radius: 8px;
            background: #eef2f7; color: var(--lf-muted); border: 1px solid var(--lf-border);
        }}
        .lf-badge.commodity {{ background: #dbeafe; color: #1d4ed8; border-color: #93c5fd; }}
        .lf-badge.weight {{ background: #dcfce7; color: #15803d; border-color: #86efac; }}
        .lf-badge.status {{ background: #ffedd5; color: #c2410c; border-color: #fdba74; }}
        .lf-traffic {{ display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.6rem; border-radius: 20px; }}
        .lf-traffic.green {{ background: #dcfce7; color: #166534; }}
        .lf-traffic.amber {{ background: #fef3c7; color: #92400e; }}
        .lf-traffic.red {{ background: #fee2e2; color: #991b1b; }}
        .lf-voice-panel {{ background: var(--lf-card); border: 1px solid var(--lf-border); border-left: 4px solid var(--lf-blue); border-radius: 14px; padding: 1rem; margin-bottom: 1rem; }}
        .lf-map-sim {{ height: 140px; background: linear-gradient(90deg, #c5d0de, #dce3ed); border-radius: 14px; border: 1px solid var(--lf-border); position: relative; margin-bottom: 1rem; overflow: hidden; }}
        .lf-map-route {{ position: absolute; top: 50%; left: 10%; right: 10%; height: 4px; background: var(--lf-orange); border-radius: 2px; transform: translateY(-50%); }}
        .lf-map-pin {{ position: absolute; top: 50%; transform: translate(-50%, -50%); font-size: 1.1rem; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.25)); }}
        .lf-map-pin.origin {{ left: 10%; }}
        .lf-map-pin.dest {{ left: 90%; }}
        .lf-map-truck {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1.7rem; animation: lf-pulse 1.6s ease-in-out infinite; }}
        @keyframes lf-pulse {{ 0%, 100% {{ opacity: 0.55; transform: translate(-50%, -50%) scale(0.92); }} 50% {{ opacity: 1; transform: translate(-50%, -50%) scale(1.08); }} }}
        .lf-map-route {{ position: absolute; top: 50%; left: 10%; right: 10%; height: 4px; background: var(--lf-orange); border-radius: 2px; transform: translateY(-50%); }}

        h1, h2, h3 {{ color: var(--lf-text) !important; }}
        .stAlert, .stInfo {{ border-radius: 14px !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_bottom_nav(screens, active: str) -> None:
    """Fixed, mobile-style bottom navigation bar."""
    st.markdown('<div class="lf-navbar">', unsafe_allow_html=True)
    cols = st.columns(len(screens))
    for col, (label, key, icon) in zip(cols, screens):
        with col:
            st.button(
                f"{icon}\n{label}",
                key=f"nav_{key}",
                type="primary" if key == active else "secondary",
                on_click=lambda k=key: st.session_state.update(screen=k),
            )
    st.markdown('</div>', unsafe_allow_html=True)


def skeleton(height: int = 64, lines: int = 1) -> None:
    """Shimmering skeleton placeholder for perceived speed."""
    for _ in range(lines):
        st.markdown(f"<div class='lf-skeleton' style='height:{height}px'></div>", unsafe_allow_html=True)


def empty_state(icon: str, title: str, sub: str = "", cta_label: str | None = None,
                cta_key: str | None = None, cta_target: str | None = None) -> None:
    """Polished empty state with icon, copy and optional CTA (navigates if cta_target)."""
    st.markdown(
        f"<div class='lf-empty'><div class='lf-empty-ico'>{icon}</div>"
        f"<div class='lf-empty-title'>{title}</div>"
        f"<div class='lf-empty-sub'>{sub}</div></div>",
        unsafe_allow_html=True,
    )
    if cta_label:
        st.button(
            cta_label,
            key=cta_key or "lf_empty_cta",
            use_container_width=True,
            on_click=lambda t=cta_target: st.session_state.update(screen=t) if t else None,
        )


def inject_ui_css(night_mode: bool = False) -> None:
    """Backwards-compatible alias for the mobile theme."""
    inject_mobile_css()