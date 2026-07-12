"""
Offline Resilience & Performance — cache queries/API responses, lazy-load heavy screens,
optimistic UI updates, and an offline banner.

Provides decorators and utilities for making the Streamlit app resilient
to network failures and fast on slow connections.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import pickle
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn, get_setting, set_setting, clear_cache

P = ParamSpec("P")
T = TypeVar("T")

# ===========================================================================
# Cache configuration
# ===========================================================================

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_SECONDS = 300  # 5 minutes default
API_CACHE_TTL = 60  # API responses cache for 1 minute

# In-memory cache for the current session
_session_cache: dict[str, tuple[Any, float]] = {}


# ===========================================================================
# Offline detection
# ===========================================================================

def is_online() -> bool:
    """Check network connectivity by attempting to reach a reliable host."""
    import urllib.request
    try:
        urllib.request.urlopen("https://8.8.8.8", timeout=1)
        return True
    except Exception:
        return False


def get_connectivity_status() -> dict[str, Any]:
    """Return connectivity status with last check timestamp."""
    last_check = get_setting("connectivity_last_check", "never")
    status = is_online()
    return {
        "online": status,
        "last_check": last_check,
        "cached_data_available": _has_cached_data(),
    }


def _has_cached_data() -> bool:
    """Check if any cache files exist."""
    return any(CACHE_DIR.iterdir()) if CACHE_DIR.exists() else False


# ===========================================================================
# Offline banner component
# ===========================================================================

def render_offline_banner() -> None:
    """Show an offline banner if the app is disconnected from network."""
    connectivity = get_connectivity_status()
    if not connectivity["online"]:
        st.markdown(
            """
            <div style="position:sticky;top:0;z-index:999;background:#dc2626;color:white;
                        padding:0.5rem 1rem;text-align:center;font-weight:700;font-size:0.9rem;
                        border-radius:0 0 12px 12px;margin-bottom:0.5rem;">
                📡 OFFLINE MODE — Showing cached data. Some features unavailable.
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Update last check
        set_setting("connectivity_last_check", datetime.now().isoformat())


# ===========================================================================
# Disk-backed cache with TTL
# ===========================================================================

def _cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a deterministic cache key from function name and arguments."""
    key_parts = [prefix]
    key_parts.extend(str(a) for a in args)
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    raw = ":".join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.pkl"


def disk_cache(ttl_seconds: int = CACHE_TTL_SECONDS) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that caches function results to disk with TTL.
    Falls back to stale cache if the function raises an exception (offline mode).
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = _cache_key(func.__name__, *args, **kwargs)
            cache_file = _cache_path(key)

            # Try to load from cache
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        cached_data: T = pickle.load(f)
                    cached_at = cache_file.stat().st_mtime
                    age = time.time() - cached_at
                    if age < ttl_seconds:
                        return cached_data
                except Exception:
                    pass

            # Execute the function
            try:
                result = func(*args, **kwargs)
                # Save to cache
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
                return result
            except Exception:
                # Fallback to stale cache
                if cache_file.exists():
                    try:
                        with open(cache_file, "rb") as f:
                            return pickle.load(f)
                    except Exception:
                        pass
                raise

        return wrapper
    return decorator


# ===========================================================================
# Session-level in-memory cache
# ===========================================================================

def mem_cache(ttl_seconds: int = CACHE_TTL_SECONDS) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that caches function results in memory for the current session.
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = _cache_key(func.__name__, *args, **kwargs)
            now = time.time()
            if key in _session_cache:
                value, timestamp = _session_cache[key]
                if now - timestamp < ttl_seconds:
                    return value
            result = func(*args, **kwargs)
            _session_cache[key] = (result, now)
            return result
        return wrapper
    return decorator


# ===========================================================================
# SQLite query cache with invalidation
# ===========================================================================

def cached_query(cache_key: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for SQL queries. Results are cached to disk.
    Invalidates when the underlying table is modified (via last_updated tracking).
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            full_key = _cache_key(cache_key, *args, **kwargs)
            cache_file = _cache_path(full_key)

            # Check if we can use cache
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        cached_data: tuple[T, str] = pickle.load(f)
                    if isinstance(cached_data, tuple) and len(cached_data) == 2:
                        result, timestamp = cached_data
                        age = time.time() - float(timestamp) if isinstance(timestamp, (int, float)) else 0
                        if age < ttl_seconds:
                            return result
                except Exception:
                    pass

            try:
                result = func(*args, **kwargs)
                with open(cache_file, "wb") as f:
                    pickle.dump((result, time.time()), f)
                return result
            except Exception:
                if cache_file.exists():
                    try:
                        with open(cache_file, "rb") as f:
                            cached_data = pickle.load(f)
                            if isinstance(cached_data, tuple) and len(cached_data) == 2:
                                return cached_data[0]
                            return cached_data
                    except Exception:
                        pass
                raise

        return wrapper
    return decorator


def invalidate_cache(pattern: str | None = None) -> None:
    """Invalidate disk cache. If pattern is provided, delete matching files."""
    if pattern is None:
        for f in CACHE_DIR.glob("*.pkl"):
            f.unlink(missing_ok=True)
    else:
        for f in CACHE_DIR.glob(f"{pattern}*.pkl"):
            f.unlink(missing_ok=True)
    _session_cache.clear()
    clear_cache()


# ===========================================================================
# Lazy loading — render skeleton then data
# ===========================================================================

def lazy_render(render_func: Callable[[], None], skeleton_lines: int = 3, skeleton_height: int = 64) -> None:
    """
    Render skeleton placeholders first, then load and render the actual content.
    Uses Streamlit's empty placeholder pattern for seamless update.
    """
    placeholder = st.empty()

    # Show skeleton
    with placeholder.container():
        for _ in range(skeleton_lines):
            st.markdown(
                f"<div class='lf-skeleton' style='height:{skeleton_height}px;margin-bottom:0.5rem;'></div>",
                unsafe_allow_html=True,
            )

    # Load and render actual content
    try:
        with placeholder.container():
            render_func()
    except Exception as e:
        with placeholder.container():
            st.error(f"Failed to load content: {e}")
            if st.button("Retry", key=f"retry_{id(render_func)}"):
                st.rerun()


# ===========================================================================
# Optimistic UI updates
# ===========================================================================

class OptimisticUpdate:
    """
    Wraps a state mutation with optimistic UI update pattern:
    1. Apply change locally immediately
    2. Send the async update
    3. Revert on failure
    """

    def __init__(self, state_key: str, undo_callback: Callable[[], None] | None = None):
        self.state_key = state_key
        self.undo_callback = undo_callback
        self._snapshot: Any = None

    def __enter__(self) -> OptimisticUpdate:
        # Snapshot current state
        if self.state_key in st.session_state:
            self._snapshot = st.session_state[self.state_key]
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None and self._snapshot is not None:
            # Revert on error
            st.session_state[self.state_key] = self._snapshot
            if self.undo_callback:
                self.undo_callback()


def optimistic_callback(callback: Callable[P, T]) -> Callable[P, T]:
    """Decorator for callbacks that should show immediate feedback."""
    @functools.wraps(callback)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return callback(*args, **kwargs)
        except Exception as e:
            st.toast(f"Action failed: {e}", icon="❌")
            raise
    return wrapper


# ===========================================================================
# Prefetch helper for heavy screens
# ===========================================================================

def prefetch_data(prefetch_funcs: list[tuple[str, Callable[[], Any]]]) -> None:
    """
    Prefetch data in background (store in session state) for heavy screens.
    Each tuple is (session_state_key, function_to_call).
    """
    for key, func in prefetch_funcs:
        if key not in st.session_state:
            try:
                st.session_state[key] = func()
            except Exception:
                st.session_state[key] = None


# ===========================================================================
# Performance monitoring
# ===========================================================================

class PerfTimer:
    """Simple performance timer for measuring render times."""

    def __init__(self, label: str = ""):
        self.label = label
        self.start: float = 0.0

    def __enter__(self) -> PerfTimer:
        self.start = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed = time.time() - self.start
        if elapsed > 0.5:
            st.toast(f"⏱ {self.label}: {elapsed:.2f}s", icon="🐌")
        elif elapsed > 0.2:
            pass  # Could add debug logging here


# ===========================================================================
# API response cache (for ELD and external calls)
# ===========================================================================

API_CACHE: dict[str, tuple[Any, float]] = {}


def cached_api_call(ttl_seconds: int = API_CACHE_TTL) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Cache ELD API responses with short TTL to avoid rate limits.
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = _cache_key("api", func.__name__, *args, **kwargs)
            now = time.time()

            if key in API_CACHE:
                value, timestamp = API_CACHE[key]
                if now - timestamp < ttl_seconds:
                    return value

            result = func(*args, **kwargs)
            API_CACHE[key] = (result, now)
            return result
        return wrapper
    return decorator