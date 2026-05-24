"""Genesis Billing tools - Phase 3 scaffolds.

Wraps the operations advertised by skill_bundles/genesis-billing.json so the
agent runtime can dispatch them without 500s. Real provider integration
(Stripe, Chargebee, QuickBooks, AP2/x402) lands in Phase 9.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from . import register_tool

log = logging.getLogger(__name__)


def _scaffold(action: str, args: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "stub": True,
        "action": action,
        "args": args,
        "note": "Phase 3 scaffold - Phase 9 integrates real provider (Stripe / Chargebee / QuickBooks)",
    }
    if extra:
        payload.update(extra)
    return payload


def _err(action: str, exc: Exception) -> dict[str, Any]:
    log.exception("billing tool %s failed", action)
    return {
        "ok": False,
        "action": action,
        "error": type(exc).__name__,
        "message": str(exc),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def billing_import_ar_ledger(
    *,
    provider: str | None = None,
    source: str | None = None,
    price: float | None = None,
    records: int | None = None,
    period: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "provider": provider or source,
            "source": source or provider,
            "price": price,
            "records": records,
            "period": period,
        }
        return _scaffold(
            "billing_import_ar_ledger",
            args,
            extra={
                "import_id": f"arimp_{uuid.uuid4().hex[:12]}",
                "records_count": records,
                "status": "imported",
            },
        )
    except Exception as e:
        return _err("billing_import_ar_ledger", e)


async def billing_run_dunning_batch(
    *,
    experiment_id: str | None = None,
    overdue_invoices: list[dict[str, Any]] | None = None,
    sequence_name: str | None = None,
    cloud_hours: float | None = None,
    hourly_rate: float | None = None,
    expected_recovery_pct: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        batch_id = experiment_id or f"dun_{uuid.uuid4().hex[:10]}"
        args = {
            "batch_id": batch_id,
            "overdue_invoices_count": len(overdue_invoices) if overdue_invoices else None,
            "sequence_name": sequence_name,
            "cloud_hours": cloud_hours,
            "hourly_rate": hourly_rate,
            "expected_recovery_pct": expected_recovery_pct,
        }
        return _scaffold(
            "billing_run_dunning_batch",
            args,
            extra={
                "batch_id": batch_id,
                "status": "scheduled",
                "expected_recovery_pct": expected_recovery_pct,
            },
        )
    except Exception as e:
        return _err("billing_run_dunning_batch", e)


async def billing_deploy_plan_change(
    *,
    channel: str | None = None,
    spend: float | None = None,
    risk_level: str | None = None,
    customer_id: str | None = None,
    new_plan: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "channel": channel,
            "spend": spend,
            "risk_level": risk_level,
            "customer_id": customer_id,
            "new_plan": new_plan,
        }
        return _scaffold(
            "billing_deploy_plan_change",
            args,
            extra={
                "deploy_id": f"planchg_{uuid.uuid4().hex[:12]}",
                "status": "pending_ap2_approval",
                "note": "Stripe / Chargebee plan switch lands in Phase 9",
            },
        )
    except Exception as e:
        return _err("billing_deploy_plan_change", e)


async def billing_generate_revops_report(
    *,
    subscriptions: list[dict[str, Any]] | None = None,
    period: str = "current",
    # legacy kwargs accepted but ignored
    dashboards: int | None = None,
    seat_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generates a RevOps report computed from a provided list of subscription dicts."""
    from datetime import datetime, timezone
    from collections import defaultdict

    try:
        subs: list[dict[str, Any]] = subscriptions or []

        if not subs:
            return {
                "ok": True,
                "report": {
                    "period": period,
                    "mrr": 0.0,
                    "arr": 0.0,
                    "active_subscriptions": 0,
                    "trial_subscriptions": 0,
                    "churned_subscriptions": 0,
                    "churn_rate_pct": 0.0,
                    "plan_breakdown": {},
                    "arpa": 0.0,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "note": "No subscription data was provided. Pass subscriptions=[...] for a real report.",
                },
            }

        mrr = 0.0
        active_count = 0
        trial_count = 0
        churned_count = 0
        plan_groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "mrr": 0.0})

        for sub in subs:
            status = str(sub.get("status", "active")).lower()
            plan = str(sub.get("plan", "unknown"))
            try:
                amount = float(sub.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0.0

            # Normalise to monthly: heuristic — if amount looks like an annual figure
            # (plan name contains "annual"/"yearly"/"year"), divide by 12.
            plan_lower = plan.lower()
            if any(k in plan_lower for k in ("annual", "yearly", "year")):
                monthly_amount = amount / 12.0
            else:
                monthly_amount = amount

            plan_groups[plan]["count"] += 1
            if status == "active":
                active_count += 1
                mrr += monthly_amount
                plan_groups[plan]["mrr"] = round(plan_groups[plan]["mrr"] + monthly_amount, 4)
            elif status == "trial":
                trial_count += 1
                plan_groups[plan]["mrr"] = round(plan_groups[plan]["mrr"], 4)
            elif status == "cancelled":
                churned_count += 1

        arr = mrr * 12.0
        denominator = active_count + churned_count
        churn_rate = (churned_count / denominator * 100.0) if denominator > 0 else 0.0
        arpa = (mrr / active_count) if active_count > 0 else 0.0

        # round plan breakdown
        plan_breakdown = {
            plan: {"count": v["count"], "mrr": round(v["mrr"], 2)}
            for plan, v in plan_groups.items()
        }

        return {
            "ok": True,
            "report": {
                "period": period,
                "mrr": round(mrr, 2),
                "arr": round(arr, 2),
                "active_subscriptions": active_count,
                "trial_subscriptions": trial_count,
                "churned_subscriptions": churned_count,
                "churn_rate_pct": round(churn_rate, 4),
                "plan_breakdown": plan_breakdown,
                "arpa": round(arpa, 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    except Exception as e:
        return _err("billing_generate_revops_report", e)


async def billing_run_billing_cycle(
    *,
    provider: str | None = None,
    dataset_price: float | None = None,
    records: int | None = None,
    cloud_hours: float | None = None,
    deployment_spend: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "provider": provider,
            "dataset_price": dataset_price,
            "records": records,
            "cloud_hours": cloud_hours,
            "deployment_spend": deployment_spend,
        }
        return _scaffold(
            "billing_run_billing_cycle",
            args,
            extra={
                "cycle_id": f"bcycle_{uuid.uuid4().hex[:12]}",
                "stages": [
                    "ar_imported",
                    "dunning_run",
                    "plan_change_deployed",
                    "revops_report_generated",
                ],
                "status": "scaffold_complete",
            },
        )
    except Exception as e:
        return _err("billing_run_billing_cycle", e)


async def billing_get_budget_metrics(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "billing_get_budget_metrics",
            "monthly_limit": 1500.00,
            "monthly_spend": 0.00,
            "remaining_budget": 1500.00,
            "window": {"start": None, "end": None},
            "note": "Phase 3 scaffold - real AP2 metrics in Phase 6",
        }
    except Exception as e:
        return _err("billing_get_budget_metrics", e)


async def billing_get_audit_log(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "billing_get_audit_log",
            "entries": [],
            "count": 0,
            "note": "Phase 3 scaffold - real AP2 audit log in Phase 6",
        }
    except Exception as e:
        return _err("billing_get_audit_log", e)


async def billing_get_alerts(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "billing_get_alerts",
            "alerts": [],
            "count": 0,
            "note": "Phase 3 scaffold - real alert engine in Phase 6",
        }
    except Exception as e:
        return _err("billing_get_alerts", e)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict[str, Any]] = {
    "billing_import_ar_ledger": {
        "type": "function",
        "function": {
            "name": "billing_import_ar_ledger",
            "description": "Import an AR/CRM dataset (subscriptions, open invoices) from Stripe/QuickBooks etc. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "source": {"type": "string"},
                    "price": {"type": "number"},
                    "records": {"type": "integer"},
                    "period": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "billing_run_dunning_batch": {
        "type": "function",
        "function": {
            "name": "billing_run_dunning_batch",
            "description": "Run a dunning/retry cycle on overdue invoices. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "overdue_invoices": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "sequence_name": {"type": "string"},
                    "cloud_hours": {"type": "number"},
                    "hourly_rate": {"type": "number"},
                    "expected_recovery_pct": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "billing_deploy_plan_change": {
        "type": "function",
        "function": {
            "name": "billing_deploy_plan_change",
            "description": "Deploy a billing-plan change to a channel (Stripe/Chargebee). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "spend": {"type": "number"},
                    "risk_level": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "new_plan": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "billing_generate_revops_report": {
        "type": "function",
        "function": {
            "name": "billing_generate_revops_report",
            "description": (
                "Produce a real RevOps report from a list of subscriptions. "
                "Computes MRR, ARR, active/trial/churned counts, churn_rate_pct, "
                "plan_breakdown (count + MRR per plan), and ARPA. "
                "Annual plans (name contains 'annual'/'yearly'/'year') are normalised to monthly. "
                "Pass an empty or omitted subscriptions list to receive a zero-value template."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subscriptions": {
                        "type": "array",
                        "description": (
                            "List of subscription objects. Each must have: "
                            "plan (string), amount (number, monthly or annual), "
                            "status ('active' | 'cancelled' | 'trial'), "
                            "start_date (ISO string). end_date is optional."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "plan": {"type": "string"},
                                "amount": {"type": "number"},
                                "status": {"type": "string", "enum": ["active", "cancelled", "trial"]},
                                "start_date": {"type": "string"},
                                "end_date": {"type": "string"},
                            },
                            "required": ["plan", "amount", "status", "start_date"],
                        },
                    },
                    "period": {"type": "string", "default": "current", "description": "Label for the report period."},
                },
                "additionalProperties": True,
            },
        },
    },
    "billing_run_billing_cycle": {
        "type": "function",
        "function": {
            "name": "billing_run_billing_cycle",
            "description": "Full billing cycle: AR import + dunning + plan change + RevOps report. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "dataset_price": {"type": "number"},
                    "records": {"type": "integer"},
                    "cloud_hours": {"type": "number"},
                    "deployment_spend": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "billing_get_budget_metrics": {
        "type": "function",
        "function": {
            "name": "billing_get_budget_metrics",
            "description": "Return monthly_limit, monthly_spend, remaining_budget, window. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "billing_get_audit_log": {
        "type": "function",
        "function": {
            "name": "billing_get_audit_log",
            "description": "Return signed AP2 audit receipts for billing operations. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "billing_get_alerts": {
        "type": "function",
        "function": {
            "name": "billing_get_alerts",
            "description": "Return per-transaction alerts crossed this session. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
}


def register() -> None:
    register_tool("billing_import_ar_ledger", billing_import_ar_ledger, _SCHEMAS["billing_import_ar_ledger"])
    register_tool("billing_run_dunning_batch", billing_run_dunning_batch, _SCHEMAS["billing_run_dunning_batch"])
    register_tool("billing_deploy_plan_change", billing_deploy_plan_change, _SCHEMAS["billing_deploy_plan_change"])
    register_tool("billing_generate_revops_report", billing_generate_revops_report, _SCHEMAS["billing_generate_revops_report"])
    register_tool("billing_run_billing_cycle", billing_run_billing_cycle, _SCHEMAS["billing_run_billing_cycle"])
    register_tool("billing_get_budget_metrics", billing_get_budget_metrics, _SCHEMAS["billing_get_budget_metrics"])
    register_tool("billing_get_audit_log", billing_get_audit_log, _SCHEMAS["billing_get_audit_log"])
    register_tool("billing_get_alerts", billing_get_alerts, _SCHEMAS["billing_get_alerts"])
