"""Simple RBAC for multi-user tenancy (Phase D-ready, works solo today).

Roles:
  owner_driver — solo O/O (default): full access
  owner       — company owner
  dispatcher   — office dispatch
  driver       — cab only (assigned loads)
  platform_admin — cross-tenant support (hosted later)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ROLE_OWNER_DRIVER = "owner_driver"
ROLE_OWNER = "owner"
ROLE_DISPATCHER = "dispatcher"
ROLE_DRIVER = "driver"
ROLE_PLATFORM_ADMIN = "platform_admin"

# action -> roles allowed
_ACL: dict[str, frozenset[str]] = {
    "load.create": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}),
    "load.edit_any": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}),
    "load.status_own": frozenset(
        {ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER, ROLE_DRIVER}
    ),
    "lead.manage": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}),
    "settings.tenant": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER}),
    "telematics.view_fleet": frozenset(
        {ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}
    ),
    "telematics.view_own": frozenset(
        {ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER, ROLE_DRIVER}
    ),
    "emergency.log": frozenset(
        {ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER, ROLE_DRIVER}
    ),
    "ai.quote": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}),
    "admin.health": frozenset({ROLE_OWNER_DRIVER, ROLE_OWNER, ROLE_DISPATCHER}),
}


@dataclass
class Principal:
    """Authenticated (or implied) actor for one request."""

    user_id: str | None
    tenant_id: str
    role: str
    display_name: str

    @property
    def is_driver_only(self) -> bool:
        return self.role == ROLE_DRIVER


def default_principal(tenant_id: str, operator_name: str = "Phillip") -> Principal:
    """Solo-fleet principal — no login required."""
    return Principal(
        user_id=None,
        tenant_id=tenant_id,
        role=ROLE_OWNER_DRIVER,
        display_name=operator_name,
    )


def can(principal: Principal, action: str, *, resource_owner_id: str | None = None) -> bool:
    """Return True if principal may perform action."""
    if principal.role == ROLE_PLATFORM_ADMIN:
        return True
    allowed = _ACL.get(action)
    if not allowed:
        return False
    if principal.role not in allowed:
        return False
    if action == "load.status_own" and principal.role == ROLE_DRIVER:
        if resource_owner_id is None:
            return True  # allow until assignment is enforced
        return resource_owner_id in (principal.user_id, principal.display_name)
    return True


def require(
    principal: Principal,
    action: str,
    *,
    resource_owner_id: str | None = None,
) -> None:
    if not can(principal, action, resource_owner_id=resource_owner_id):
        raise PermissionError(f"Role {principal.role!r} cannot {action}")


def current_principal() -> Principal:
    """Resolve principal from session (Phase B: always owner_driver)."""
    from lp_helpers.tenancy import current_tenant_id

    tenant_id = current_tenant_id()
    name = "Phillip"
    role = ROLE_OWNER_DRIVER
    try:
        import streamlit as st

        name = str(st.session_state.get("owner_role") or name)
        role = str(st.session_state.get("user_role") or role)
        if "tenant_id" not in st.session_state:
            st.session_state["tenant_id"] = tenant_id
    except Exception:
        pass
    return Principal(
        user_id=None,
        tenant_id=tenant_id,
        role=role if role in _ACL.get("load.create", frozenset()) or role == ROLE_DRIVER else ROLE_OWNER_DRIVER,
        display_name=name,
    )
