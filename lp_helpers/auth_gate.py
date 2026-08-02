"""Lightweight password gate for public URL deployments.

If no password is configured (secrets or env), gate is disabled (local solo mode).
"""

from __future__ import annotations

import hmac
import os
from typing import Any


def resolve_app_password(
    *,
    secrets_getter: Any | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Return configured app password or empty string if unset.

    secrets_getter: callable(section, key, default='') or None.
    When secrets_getter is None, only env is checked.
    """
    env = env if env is not None else dict(os.environ)
    env_pw = str(env.get("LP_APP_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    if secrets_getter is not None:
        try:
            pw = secrets_getter("auth", "password", "")
            if pw:
                return str(pw).strip()
        except Exception:
            pass
    return ""


def password_required(password: str | None) -> bool:
    """True when a non-empty password is configured."""
    return bool(password and str(password).strip())


def verify_password(provided: str, expected: str) -> bool:
    """Constant-time password compare via hmac.compare_digest.

    Empty expected never authenticates. Different-length inputs are hashed
    first so compare_digest always runs (avoids length early-out).
    """
    if not expected:
        return False
    import hashlib

    a = hashlib.sha256((provided or "").encode("utf-8")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def check_password_digest(provided: str, expected: str) -> bool:
    """Alias for tests — uses hmac.compare_digest path."""
    return verify_password(provided, expected)
