"""Multi-fleet / multi-company foundation (phased, non-breaking).

Phase A (current): single default tenant = L&P Freight.
Phase B: resolve tenant from session / login / subdomain.
Phase C: scope all DB queries by tenant_id.

Do not break the current single-tenant deploy — call get_tenant_context()
where branding or operator lists are needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
            tenant_id="lp-freight",
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
        tenant_id="lp-freight",
        carrier_name=CARRIER_NAME,
        platform_title=PLATFORM_TITLE,
        operators=tuple(OWNERS),
        default_operator=DEFAULT_OWNER,
        primary_lane_origin="Spruce Pine, NC",
        primary_lane_dest="Central Georgia (Kohler area)",
        trailer_desc=TRAILER_DESC,
        truck_label=TRUCK_LABEL,
        metadata={"legacy_profile": "lawson_profile"},
    )


def get_tenant_context(tenant_id: str | None = None) -> TenantContext:
    """Resolve tenant. Phase A: always default. Phase B: lookup registry."""
    # Future: load from DB / secrets by tenant_id or st.session_state["tenant_id"]
    _ = tenant_id
    return get_default_tenant()


def list_known_tenants() -> list[TenantContext]:
    """Registry of tenants available to this deployment (Phase B expands this)."""
    return [get_default_tenant()]
