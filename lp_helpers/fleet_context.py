"""Multi-fleet / multi-company foundation (phased, non-breaking).

Phase A: single default tenant = L&P Freight (profile defaults).
Phase B: session tenant_id + DB tenants row (this module).
Phase C: all queries filter by tenant_id (repositories).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lp_helpers.tenancy import DEFAULT_TENANT_ID


@dataclass(frozen=True)
class TenantContext:
    """Scoped identity for one carrier/fleet tenant."""

    tenant_id: str
    carrier_name: str
    platform_title: str
    operators: tuple[str, ...]
    default_operator: str
    primary_lane_origin: str
    primary_lane_dest: str
    trailer_desc: str
    truck_label: str
    metadata: dict[str, Any] = field(default_factory=dict)


def get_default_tenant() -> TenantContext:
    """Current production tenant — L&P Freight single operation."""
    try:
        from lp_helpers.lawson_profile import (
            CARRIER_NAME,
            DEFAULT_OWNER,
            OWNERS,
            PLATFORM_TITLE,
            TRAILER_DESC,
            TRUCK_LABEL,
        )
    except ImportError:
        return TenantContext(
            tenant_id=DEFAULT_TENANT_ID,
            carrier_name="L & P Freight",
            platform_title="L & P Freight Platform",
            operators=("Phillip", "Lawson"),
            default_operator="Phillip",
            primary_lane_origin="Spruce Pine, NC",
            primary_lane_dest="Central Georgia (Kohler area)",
            trailer_desc="39ft Frameless End-Dump",
            truck_label="L&P End-Dump",
        )

    return TenantContext(
        tenant_id=DEFAULT_TENANT_ID,
        carrier_name=CARRIER_NAME,
        platform_title=PLATFORM_TITLE,
        operators=tuple(OWNERS),
        default_operator=DEFAULT_OWNER,
        primary_lane_origin="Spruce Pine, NC",
        primary_lane_dest="Central Georgia (Kohler area)",
        trailer_desc=TRAILER_DESC,
        truck_label=TRUCK_LABEL,
        metadata={"legacy_profile": "lawson_profile", "phase": "B"},
    )


def _load_tenant_from_db(tenant_id: str) -> TenantContext | None:
    try:
        from contextlib import closing

        from lp_helpers.database import get_conn

        with closing(get_conn()) as conn:
            row = conn.execute(
                "SELECT id, name, slug, status, plan, settings_json FROM tenants WHERE id = ?",
                (tenant_id,),
            ).fetchone()
        if not row:
            return None
        base = get_default_tenant()
        return TenantContext(
            tenant_id=str(row["id"]),
            carrier_name=str(row["name"] or base.carrier_name),
            platform_title=base.platform_title,
            operators=base.operators,
            default_operator=base.default_operator,
            primary_lane_origin=base.primary_lane_origin,
            primary_lane_dest=base.primary_lane_dest,
            trailer_desc=base.trailer_desc,
            truck_label=base.truck_label,
            metadata={
                **base.metadata,
                "slug": row["slug"],
                "status": row["status"],
                "plan": row["plan"],
                "source": "db",
            },
        )
    except Exception:
        return None


def get_tenant_context(tenant_id: str | None = None) -> TenantContext:
    """Resolve tenant for this request/session."""
    tid = tenant_id
    if not tid:
        try:
            import streamlit as st

            tid = st.session_state.get("tenant_id")
        except Exception:
            tid = None
    tid = str(tid or DEFAULT_TENANT_ID)

    db_ctx = _load_tenant_from_db(tid)
    if db_ctx:
        return db_ctx
    default = get_default_tenant()
    if tid != default.tenant_id:
        # Unknown id → still return default to avoid breaking solo deploy
        return default
    return default


def list_known_tenants() -> list[TenantContext]:
    """Registry of tenants available to this deployment."""
    try:
        from contextlib import closing

        from lp_helpers.database import get_conn

        with closing(get_conn()) as conn:
            rows = conn.execute(
                "SELECT id FROM tenants WHERE status = 'active' ORDER BY name"
            ).fetchall()
        if rows:
            return [get_tenant_context(str(r["id"])) for r in rows]
    except Exception:
        pass
    return [get_default_tenant()]


def ensure_session_tenant() -> str:
    """Bind session to default tenant (Phase B). Returns tenant_id."""
    ctx = get_tenant_context()
    try:
        import streamlit as st

        st.session_state.setdefault("tenant_id", ctx.tenant_id)
        return str(st.session_state["tenant_id"])
    except Exception:
        return ctx.tenant_id
