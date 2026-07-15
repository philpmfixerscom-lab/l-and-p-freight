"""Mobile PWA + responsive web helpers for L & P Freight Platform."""

from __future__ import annotations

import json
import os
from typing import Callable

import streamlit as st
import streamlit.components.v1 as components

from lp_helpers.database import APP_VERSION, TRAILER_PROFILE

# (short label shown in nav, full internal tab key)
MOBILE_TAB_OPTIONS: list[tuple[str, str]] = [
    ("🏠 Home", "Dashboard"),
    ("📞 Leads", "Leads CRM"),
    ("📋 Loads", "Load Logger + Matcher"),
    ("💰 Rates", "Rate Calculator"),
    ("📄 BOL", "BOL Generator"),
]

PWA_NAME = "L & P Freight"
PWA_SHORT_NAME = "L&P Freight"
PWA_DESCRIPTION = (
    "Spruce Pine NC → Central Georgia dispatch command center. "
    "Log loads, track leads, quote rates, generate BOLs."
)
PWA_THEME_COLOR = "#e85d04"
PWA_BG_COLOR = "#0b1628"


def app_base_url() -> str:
    """Public URL for PWA manifest (set LP_APP_URL in production)."""
    return os.environ.get("LP_APP_URL", "http://127.0.0.1:8502").rstrip("/")


def app_start_url() -> str:
    """PWA launch URL — /app/ when behind nginx website, / for direct Streamlit."""
    base = app_base_url()
    if os.environ.get("LP_WEB_MODE", "").lower() in ("1", "true", "yes"):
        return f"{base}/app/"
    return f"{base}/"


def driver_start_url() -> str:
    """Driver view launch URL."""
    base = app_start_url()
    if "?" in base:
        return f"{base}&view=driver"
    return f"{base}?view=driver"


def _manifest_json(base_url: str) -> str:
    start = app_start_url()
    manifest = {
        "name": PWA_NAME,
        "short_name": PWA_SHORT_NAME,
        "description": PWA_DESCRIPTION,
        "start_url": start,
        "scope": f"{base_url}/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": PWA_BG_COLOR,
        "theme_color": PWA_THEME_COLOR,
        "categories": ["business", "productivity", "utilities"],
        "icons": [
            {
                "src": f"{base_url}/static/icon-192.svg",
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": f"{base_url}/static/icon-512.svg",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "maskable",
            },
        ],
    }
    return json.dumps(manifest)


def inject_pwa_head() -> None:
    """Inject PWA meta tags, manifest, and service-worker registration."""
    base = app_base_url()
    manifest = _manifest_json(base).replace("<", "\\u003c")
    components.html(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const head = doc.head || doc.getElementsByTagName('head')[0];
            if (!head || head.querySelector('[data-lp-pwa]')) return;

            const meta = [
                ['viewport', 'width=device-width, initial-scale=1, maximum-scale=5, viewport-fit=cover, user-scalable=yes'],
                ['mobile-web-app-capable', 'yes'],
                ['apple-mobile-web-app-capable', 'yes'],
                ['apple-mobile-web-app-status-bar-style', 'black-translucent'],
                ['apple-mobile-web-app-title', '{PWA_SHORT_NAME}'],
                ['theme-color', '{PWA_THEME_COLOR}'],
                ['application-name', '{PWA_SHORT_NAME}'],
            ];
            meta.forEach(([name, content]) => {{
                const el = doc.createElement('meta');
                if (name === 'viewport') el.name = 'viewport';
                else el.name = name;
                el.content = content;
                el.setAttribute('data-lp-pwa', '1');
                head.appendChild(el);
            }});

            const manifestEl = doc.createElement('link');
            manifestEl.rel = 'manifest';
            manifestEl.href = 'data:application/manifest+json,{manifest}';
            manifestEl.setAttribute('data-lp-pwa', '1');
            head.appendChild(manifestEl);

            const apple = doc.createElement('link');
            apple.rel = 'apple-touch-icon';
            apple.href = '{base}/static/icon-192.svg';
            apple.setAttribute('data-lp-pwa', '1');
            head.appendChild(apple);

            if ('serviceWorker' in navigator) {{
                navigator.serviceWorker.register('{base}/static/sw.js', {{ scope: '/' }})
                    .catch(() => {{}});
            }}
        }})();
        </script>
        """,
        height=0,
    )


def inject_mobile_css() -> None:
    """Mobile-first layout: bottom nav, thumb zone, safe areas, collapsed sidebar."""
    st.markdown(
        """
        <style>
        /* ── Mobile shell ── */
        @media (max-width: 768px) {
            .block-container {
                padding: 0.75rem 0.85rem 6.5rem !important;
                max-width: 100% !important;
            }
            section[data-testid="stSidebar"] {
                min-width: 85vw !important;
                max-width: 85vw !important;
            }
            section[data-testid="stSidebar"][aria-expanded="false"] {
                margin-left: calc(-85vw - 2rem) !important;
            }
            .lf-topbar {
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 0.35rem;
                padding: 0.75rem 1rem !important;
            }
            .lf-kpi-grid { grid-template-columns: repeat(2, 1fr) !important; }
            div[data-testid="column"] { min-width: 100% !important; }
            .stButton > button,
            .stDownloadButton > button {
                min-height: 56px !important;
                font-size: 1.05rem !important;
            }
            .stTextInput input, .stNumberInput input, .stTextArea textarea,
            .stSelectbox > div > div {
                min-height: 52px !important;
                font-size: 16px !important; /* prevents iOS zoom */
            }
            div[data-testid="stDataFrame"] { overflow-x: auto !important; }
            h1 { font-size: 1.5rem !important; }
            h2 { font-size: 1.25rem !important; }
            h3 { font-size: 1.1rem !important; }
        }

        /* ── Bottom tab bar (mobile) ── */
        @media (max-width: 768px) {
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[data-testid="stRadio"] {
                position: fixed !important;
                bottom: 0 !important;
                left: 0 !important;
                right: 0 !important;
                z-index: 999990 !important;
                background: var(--lf-card, #e8edf4) !important;
                border-top: 2px solid var(--lf-border, #e2e8f0) !important;
                padding: 0.35rem 0.25rem calc(0.35rem + env(safe-area-inset-bottom)) !important;
                margin: 0 !important;
                box-shadow: 0 -4px 24px rgba(0,0,0,0.12) !important;
            }
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[data-testid="stRadio"] > label {
                display: none !important;
            }
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[role="radiogroup"] {
                display: flex !important;
                flex-direction: row !important;
                justify-content: space-around !important;
                gap: 0 !important;
                width: 100% !important;
            }
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[role="radiogroup"] label {
                flex: 1 !important;
                text-align: center !important;
                padding: 0.5rem 0.15rem !important;
                margin: 0 !important;
                border: none !important;
                border-radius: 10px !important;
                background: transparent !important;
                font-size: 0.72rem !important;
                font-weight: 700 !important;
                min-height: 52px !important;
                line-height: 1.2 !important;
            }
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[role="radiogroup"] label[data-checked="true"],
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[role="radiogroup"] label:has(input:checked) {
                background: rgba(232,93,4,0.15) !important;
                color: var(--lf-orange, #e85d04) !important;
            }
        }

        /* ── Desktop: horizontal scroll tabs ── */
        @media (min-width: 769px) {
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[data-testid="stRadio"] div[role="radiogroup"] {
                display: flex !important;
                flex-wrap: nowrap !important;
                overflow-x: auto !important;
                gap: 0.35rem !important;
                padding-bottom: 0.25rem !important;
            }
            .lf-mobile-nav-anchor + div[data-testid="stVerticalBlock"] div[role="radiogroup"] label {
                flex-shrink: 0 !important;
                min-height: 48px !important;
                padding: 0.6rem 1rem !important;
                border-radius: 10px !important;
                border: 1px solid var(--lf-border) !important;
            }
        }

        /* Install prompt banner */
        .lf-install-banner {
            display: none;
            position: fixed;
            bottom: calc(4.5rem + env(safe-area-inset-bottom));
            left: 0.75rem; right: 0.75rem;
            background: var(--lf-navy, #0b1628);
            color: #fff;
            border-radius: 12px;
            padding: 0.85rem 1rem;
            z-index: 999989;
            box-shadow: 0 8px 32px rgba(0,0,0,0.25);
            font-size: 0.9rem;
        }
        .lf-install-banner.show { display: block; }
        .lf-install-banner button {
            background: var(--lf-orange, #e85d04);
            color: #fff; border: none; border-radius: 8px;
            padding: 0.5rem 1rem; font-weight: 700; margin-top: 0.5rem;
            width: 100%; min-height: 48px; cursor: pointer;
        }
        @media (min-width: 769px) { .lf-install-banner { bottom: 1rem; max-width: 360px; left: auto; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_mobile_shell_js() -> None:
    """Collapse sidebar on phone, show PWA install prompt."""
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            const mq = window.matchMedia('(max-width: 768px)');

            function collapseSidebar() {
                if (!mq.matches) return;
                const collapse = doc.querySelector('[data-testid="collapsedControl"]');
                if (collapse && doc.querySelector('section[data-testid="stSidebar"][aria-expanded="true"]')) {
                    collapse.click();
                }
            }
            setTimeout(collapseSidebar, 400);

            let deferredPrompt;
            window.addEventListener('beforeinstallprompt', (e) => {
                e.preventDefault();
                deferredPrompt = e;
                const banner = doc.getElementById('lf-install-banner');
                if (banner) banner.classList.add('show');
            });

            doc.addEventListener('click', (e) => {
                if (e.target && e.target.id === 'lf-install-btn' && deferredPrompt) {
                    deferredPrompt.prompt();
                    deferredPrompt = null;
                    const banner = doc.getElementById('lf-install-banner');
                    if (banner) banner.classList.remove('show');
                }
                if (e.target && e.target.id === 'lf-install-dismiss') {
                    const banner = doc.getElementById('lf-install-banner');
                    if (banner) banner.classList.remove('show');
                }
            });
        })();
        </script>
        <div id="lf-install-banner" class="lf-install-banner">
            <strong>Install L &amp; P Freight</strong><br>
            Add to your home screen for cab-ready dispatch.
            <button id="lf-install-btn">Install App</button>
            <button id="lf-install-dismiss" style="background:transparent;color:#94a3b8;margin-top:0.25rem;">Not now</button>
        </div>
        """,
        height=0,
    )


def render_mobile_tab_nav(
    tab_options: list[str],
    active_tab: str,
    *,
    key: str = "mobile_main_nav",
) -> str:
    """
    Render thumb-friendly tab nav. Returns the selected full tab name.
    Uses short labels on all screen sizes for consistency.
    """
    label_to_full = {short: full for short, full in MOBILE_TAB_OPTIONS if full in tab_options}
    if not label_to_full:
        label_to_full = {t: t for t in tab_options}

    short_labels = [short for short, full in MOBILE_TAB_OPTIONS if full in tab_options]
    if not short_labels:
        short_labels = tab_options
        label_to_full = {t: t for t in tab_options}

    full_to_short = {v: k for k, v in label_to_full.items()}
    default_short = full_to_short.get(active_tab, short_labels[0])

    st.markdown('<div class="lf-mobile-nav-anchor"></div>', unsafe_allow_html=True)
    choice = st.radio(
        "Navigation",
        short_labels,
        index=short_labels.index(default_short) if default_short in short_labels else 0,
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    return label_to_full.get(choice, choice)


def render_mobile_quick_actions(
    actions: list[tuple[str, str, str]],
    on_nav: Callable[[str], None],
) -> None:
    """Render a grid of large touch-friendly quick-action buttons."""
    st.markdown('<div class="lf-section-header">Quick Actions</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(actions), 2))
    for i, (label, tab, icon) in enumerate(actions):
        with cols[i % len(cols)]:
            if st.button(f"{icon} {label}", use_container_width=True, key=f"qa_{tab}"):
                on_nav(tab)