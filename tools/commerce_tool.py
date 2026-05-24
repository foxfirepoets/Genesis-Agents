"""Genesis Commerce tools - Phase 3 scaffolds.

Wraps the operations advertised by skill_bundles/genesis-commerce.json so the
agent runtime can dispatch them without 500s. Real provider integration
(Namecheap, Stripe, Avalara, Shippo, AP2/x402) lands in Phase 9.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from . import register_tool

log = logging.getLogger(__name__)


def _scaffold(action: str, args: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a uniform Phase 3 scaffold response."""
    payload: dict[str, Any] = {
        "ok": True,
        "stub": True,
        "action": action,
        "args": args,
        "note": "Phase 3 scaffold - Phase 9 integrates real provider",
    }
    if extra:
        payload.update(extra)
    return payload


def _err(action: str, exc: Exception) -> dict[str, Any]:
    log.exception("commerce tool %s failed", action)
    return {
        "ok": False,
        "action": action,
        "error": type(exc).__name__,
        "message": str(exc),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def commerce_register_domain(
    *,
    domain: str | None = None,
    owner_info: dict[str, Any] | None = None,
    registrar: str = "namecheap",
    registration_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "domain": domain,
            "owner_info": owner_info,
            "registrar": registrar,
            "registration_cost": registration_cost,
        }
        return _scaffold(
            "commerce_register_domain",
            args,
            extra={
                "registration_id": f"reg_{uuid.uuid4().hex[:12]}",
                "registrar": registrar,
                "domain": domain,
                "status": "pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("commerce_register_domain", e)


async def commerce_activate_payment_gateway(
    *,
    provider: str | None = None,
    gateway: str | None = None,
    account_info: dict[str, Any] | None = None,
    setup_fee: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "provider": provider or gateway,
            "gateway": gateway or provider,
            "account_info": account_info,
            "setup_fee": setup_fee,
        }
        return _scaffold(
            "commerce_activate_payment_gateway",
            args,
            extra={
                "activation_id": f"gw_{uuid.uuid4().hex[:12]}",
                "status": "pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("commerce_activate_payment_gateway", e)


async def commerce_configure_tax_engine(
    *,
    region: str | None = None,
    provider: str | None = None,
    tax_rules: list[dict[str, Any]] | None = None,
    monthly_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "region": region,
            "provider": provider or "avalara",
            "tax_rules": tax_rules,
            "monthly_cost": monthly_cost,
        }
        return _scaffold(
            "commerce_configure_tax_engine",
            args,
            extra={
                "config_id": f"tax_{uuid.uuid4().hex[:12]}",
                "status": "configured",
            },
        )
    except Exception as e:
        return _err("commerce_configure_tax_engine", e)


async def commerce_ship_fulfillment_batch(
    *,
    shipments: list[dict[str, Any]] | None = None,
    carrier: str | None = None,
    orders: list[dict[str, Any]] | None = None,
    per_order_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        all_orders = shipments or orders or []
        args = {
            "shipments": shipments,
            "carrier": carrier or "shippo",
            "orders": orders,
            "per_order_cost": per_order_cost,
        }
        return _scaffold(
            "commerce_ship_fulfillment_batch",
            args,
            extra={
                "batch_id": f"ship_{uuid.uuid4().hex[:12]}",
                "order_count": len(all_orders),
                "status": "queued",
            },
        )
    except Exception as e:
        return _err("commerce_ship_fulfillment_batch", e)


async def commerce_launch_commerce_stack(
    *,
    config: dict[str, Any] | None = None,
    domain: str | None = None,
    registrar_cost: float | None = None,
    gateway_fee: float | None = None,
    tax_engine_cost: float | None = None,
    fulfillment_orders: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "config": config,
            "domain": domain,
            "registrar_cost": registrar_cost,
            "gateway_fee": gateway_fee,
            "tax_engine_cost": tax_engine_cost,
            "fulfillment_orders": fulfillment_orders,
        }
        return _scaffold(
            "commerce_launch_commerce_stack",
            args,
            extra={
                "launch_id": f"launch_{uuid.uuid4().hex[:12]}",
                "stages": [
                    "domain_registered",
                    "gateway_activated",
                    "tax_engine_configured",
                    "fulfillment_ready",
                ],
                "status": "scaffold_complete",
            },
        )
    except Exception as e:
        return _err("commerce_launch_commerce_stack", e)


async def commerce_get_budget_metrics(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "commerce_get_budget_metrics",
            "monthly_limit": 1500.00,
            "monthly_spend": 0.00,
            "remaining_budget": 1500.00,
            "window": {"start": None, "end": None},
            "note": "Phase 3 scaffold - real AP2 metrics in Phase 6",
        }
    except Exception as e:
        return _err("commerce_get_budget_metrics", e)


async def commerce_get_audit_log(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "commerce_get_audit_log",
            "entries": [],
            "count": 0,
            "note": "Phase 3 scaffold - real AP2 audit log in Phase 6",
        }
    except Exception as e:
        return _err("commerce_get_audit_log", e)


async def commerce_get_alerts(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "commerce_get_alerts",
            "alerts": [],
            "count": 0,
            "note": "Phase 3 scaffold - real alert engine in Phase 6",
        }
    except Exception as e:
        return _err("commerce_get_alerts", e)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict[str, Any]] = {
    "commerce_register_domain": {
        "type": "function",
        "function": {
            "name": "commerce_register_domain",
            "description": "Register a domain through a registrar with AP2 budget approval and staged x402 authorization (Phase 3 scaffold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "owner_info": {"type": "object", "additionalProperties": True},
                    "registrar": {"type": "string", "default": "namecheap"},
                    "registration_cost": {"type": "number"},
                },
                "required": ["domain"],
                "additionalProperties": True,
            },
        },
    },
    "commerce_activate_payment_gateway": {
        "type": "function",
        "function": {
            "name": "commerce_activate_payment_gateway",
            "description": "Activate a payment gateway (Stripe, etc.) with AP2-gated setup fee (Phase 3 scaffold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "gateway": {"type": "string"},
                    "account_info": {"type": "object", "additionalProperties": True},
                    "setup_fee": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "commerce_configure_tax_engine": {
        "type": "function",
        "function": {
            "name": "commerce_configure_tax_engine",
            "description": "Configure a tax-engine provider (Avalara default) with monthly-cost AP2 approval (Phase 3 scaffold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "provider": {"type": "string"},
                    "tax_rules": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "monthly_cost": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "commerce_ship_fulfillment_batch": {
        "type": "function",
        "function": {
            "name": "commerce_ship_fulfillment_batch",
            "description": "Dispatch a fulfillment batch through a carrier (Shippo default) at per-order cost (Phase 3 scaffold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "shipments": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "carrier": {"type": "string"},
                    "orders": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "per_order_cost": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "commerce_launch_commerce_stack": {
        "type": "function",
        "function": {
            "name": "commerce_launch_commerce_stack",
            "description": "Full commerce-stack launch: domain + gateway + tax + fulfillment (Phase 3 scaffold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {"type": "object", "additionalProperties": True},
                    "domain": {"type": "string"},
                    "registrar_cost": {"type": "number"},
                    "gateway_fee": {"type": "number"},
                    "tax_engine_cost": {"type": "number"},
                    "fulfillment_orders": {"type": "integer"},
                },
                "additionalProperties": True,
            },
        },
    },
    "commerce_get_budget_metrics": {
        "type": "function",
        "function": {
            "name": "commerce_get_budget_metrics",
            "description": "Return monthly_limit, monthly_spend, remaining_budget, and current budget window (Phase 3 scaffold).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "commerce_get_audit_log": {
        "type": "function",
        "function": {
            "name": "commerce_get_audit_log",
            "description": "Return signed AP2 audit receipts for this session (Phase 3 scaffold).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "commerce_get_alerts": {
        "type": "function",
        "function": {
            "name": "commerce_get_alerts",
            "description": "Return per-transaction alerts crossed during the session (Phase 3 scaffold).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
}


def register() -> None:
    register_tool("commerce_register_domain", commerce_register_domain, _SCHEMAS["commerce_register_domain"])
    register_tool("commerce_activate_payment_gateway", commerce_activate_payment_gateway, _SCHEMAS["commerce_activate_payment_gateway"])
    register_tool("commerce_configure_tax_engine", commerce_configure_tax_engine, _SCHEMAS["commerce_configure_tax_engine"])
    register_tool("commerce_ship_fulfillment_batch", commerce_ship_fulfillment_batch, _SCHEMAS["commerce_ship_fulfillment_batch"])
    register_tool("commerce_launch_commerce_stack", commerce_launch_commerce_stack, _SCHEMAS["commerce_launch_commerce_stack"])
    register_tool("commerce_get_budget_metrics", commerce_get_budget_metrics, _SCHEMAS["commerce_get_budget_metrics"])
    register_tool("commerce_get_audit_log", commerce_get_audit_log, _SCHEMAS["commerce_get_audit_log"])
    register_tool("commerce_get_alerts", commerce_get_alerts, _SCHEMAS["commerce_get_alerts"])
