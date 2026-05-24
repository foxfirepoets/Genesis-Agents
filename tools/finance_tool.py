"""Genesis Finance tools - Phase 3 scaffolds.

Wraps the operations advertised by skill_bundles/genesis-finance.json so the
agent runtime can dispatch them without 500s. Real provider integration
(payroll, AR/AP, bank feeds, AP2/x402) lands in Phase 9.
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
        "note": "Phase 3 scaffold - Phase 9 integrates real provider",
    }
    if extra:
        payload.update(extra)
    return payload


def _err(action: str, exc: Exception) -> dict[str, Any]:
    log.exception("finance tool %s failed", action)
    return {
        "ok": False,
        "action": action,
        "error": type(exc).__name__,
        "message": str(exc),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def finance_run_payroll_batch(
    *,
    employees: list[dict[str, Any]] | None = None,
    employee_count: int | None = None,
    cost_per_employee: float | None = None,
    period: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        count = employee_count if employee_count is not None else (len(employees) if employees else 0)
        args = {
            "employees": employees,
            "employee_count": count,
            "cost_per_employee": cost_per_employee,
            "period": period,
        }
        return _scaffold(
            "finance_run_payroll_batch",
            args,
            extra={
                "batch_id": f"payroll_{uuid.uuid4().hex[:12]}",
                "employee_count": count,
                "status": "queued_pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("finance_run_payroll_batch", e)


async def finance_process_vendor_invoice(
    *,
    invoice: dict[str, Any] | None = None,
    vendor: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "invoice": invoice,
            "vendor": vendor or (invoice or {}).get("vendor"),
            "amount": amount if amount is not None else (invoice or {}).get("amount"),
            "category": category or (invoice or {}).get("category"),
        }
        return _scaffold(
            "finance_process_vendor_invoice",
            args,
            extra={
                "invoice_id": f"inv_{uuid.uuid4().hex[:12]}",
                "status": "scheduled_pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("finance_process_vendor_invoice", e)


async def finance_sync_bank_fees(
    *,
    account: str | None = None,
    fee_amount: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {"account": account, "fee_amount": fee_amount}
        return _scaffold(
            "finance_sync_bank_fees",
            args,
            extra={
                "sync_id": f"banksync_{uuid.uuid4().hex[:12]}",
                "status": "reconciled",
            },
        )
    except Exception as e:
        return _err("finance_sync_bank_fees", e)


async def finance_generate_finance_report(
    *,
    transactions: list[dict[str, Any]] | None = None,
    period: str = "current",
    currency: str = "USD",
    # legacy kwargs accepted but ignored
    month: str | None = None,
    format: str = "json",
    tooling_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generates a P&L report from a provided list of transaction dicts."""
    from datetime import datetime, timezone
    from collections import defaultdict

    try:
        txs: list[dict[str, Any]] = transactions or []

        if not txs:
            return {
                "ok": True,
                "report": {
                    "period": period,
                    "currency": currency,
                    "total_income": 0.0,
                    "total_expenses": 0.0,
                    "net_profit": 0.0,
                    "profit_margin_pct": 0.0,
                    "expense_breakdown": {},
                    "monthly_breakdown": [],
                    "top_expenses": [],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "transaction_count": 0,
                    "note": "No transaction data was provided. Pass transactions=[...] for a real report.",
                },
            }

        total_income = 0.0
        total_expenses = 0.0
        expense_groups: dict[str, float] = defaultdict(float)
        monthly_income: dict[str, float] = defaultdict(float)
        monthly_expenses: dict[str, float] = defaultdict(float)
        expense_items: list[dict[str, Any]] = []

        for tx in txs:
            tx_type = str(tx.get("type", "")).lower()
            try:
                amount = float(tx.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0.0

            # monthly bucketing
            raw_date = tx.get("date", "")
            try:
                month_key = str(raw_date)[:7]  # "YYYY-MM"
                if len(month_key) < 7:
                    month_key = "unknown"
            except Exception:
                month_key = "unknown"

            if tx_type == "income":
                total_income += amount
                monthly_income[month_key] += amount
            elif tx_type == "expense":
                total_expenses += amount
                monthly_expenses[month_key] += amount
                # group by first word of description
                description = str(tx.get("description", "other"))
                group = description.split()[0] if description.split() else "other"
                expense_groups[group] += amount
                expense_items.append({"description": description, "amount": amount, "date": raw_date})
            # transfers are skipped from income/expense totals

        net_profit = total_income - total_expenses
        profit_margin = (net_profit / total_income * 100.0) if total_income > 0 else 0.0

        # monthly breakdown: union of all months seen
        all_months = sorted(set(list(monthly_income.keys()) + list(monthly_expenses.keys())))
        monthly_breakdown = [
            {
                "month": m,
                "income": round(monthly_income.get(m, 0.0), 2),
                "expenses": round(monthly_expenses.get(m, 0.0), 2),
                "net": round(monthly_income.get(m, 0.0) - monthly_expenses.get(m, 0.0), 2),
            }
            for m in all_months
        ]

        top_expenses = sorted(expense_items, key=lambda x: x["amount"], reverse=True)[:5]

        return {
            "ok": True,
            "report": {
                "period": period,
                "currency": currency,
                "total_income": round(total_income, 2),
                "total_expenses": round(total_expenses, 2),
                "net_profit": round(net_profit, 2),
                "profit_margin_pct": round(profit_margin, 4),
                "expense_breakdown": {k: round(v, 2) for k, v in expense_groups.items()},
                "monthly_breakdown": monthly_breakdown,
                "top_expenses": top_expenses,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "transaction_count": len(txs),
            },
        }
    except Exception as e:
        return _err("finance_generate_finance_report", e)


async def finance_run_finance_close(
    *,
    employee_count: int | None = None,
    cost_per_employee: float | None = None,
    vendor_amount: float | None = None,
    category: str | None = None,
    bank_fee: float | None = None,
    period: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "employee_count": employee_count,
            "cost_per_employee": cost_per_employee,
            "vendor_amount": vendor_amount,
            "category": category,
            "bank_fee": bank_fee,
            "period": period,
        }
        return _scaffold(
            "finance_run_finance_close",
            args,
            extra={
                "close_id": f"close_{uuid.uuid4().hex[:12]}",
                "stages": [
                    "payroll_run",
                    "vendor_invoices_processed",
                    "bank_fees_synced",
                    "finance_report_generated",
                ],
                "status": "scaffold_complete",
            },
        )
    except Exception as e:
        return _err("finance_run_finance_close", e)


async def finance_import_x402_transactions(
    *,
    transactions: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        txs = transactions or []
        args = {"transactions_count": len(txs)}
        return _scaffold(
            "finance_import_x402_transactions",
            args,
            extra={
                "import_id": f"x402imp_{uuid.uuid4().hex[:12]}",
                "imported": len(txs),
                "status": "ingested",
            },
        )
    except Exception as e:
        return _err("finance_import_x402_transactions", e)


async def finance_get_budget_metrics(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "finance_get_budget_metrics",
            "monthly_limit": 15000.00,
            "monthly_spend": 0.00,
            "remaining_budget": 15000.00,
            "window": {"start": None, "end": None},
            "note": "Phase 3 scaffold - real AP2 metrics in Phase 6",
        }
    except Exception as e:
        return _err("finance_get_budget_metrics", e)


async def finance_get_audit_log(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "finance_get_audit_log",
            "entries": [],
            "count": 0,
            "note": "Phase 3 scaffold - real AP2 audit log in Phase 6",
        }
    except Exception as e:
        return _err("finance_get_audit_log", e)


async def finance_get_alerts(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "finance_get_alerts",
            "alerts": [],
            "count": 0,
            "note": "Phase 3 scaffold - real alert engine in Phase 6",
        }
    except Exception as e:
        return _err("finance_get_alerts", e)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict[str, Any]] = {
    "finance_run_payroll_batch": {
        "type": "function",
        "function": {
            "name": "finance_run_payroll_batch",
            "description": "Run a payroll batch (AP2-gated + x402 charged). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employees": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "employee_count": {"type": "integer"},
                    "cost_per_employee": {"type": "number"},
                    "period": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_process_vendor_invoice": {
        "type": "function",
        "function": {
            "name": "finance_process_vendor_invoice",
            "description": "Schedule a vendor invoice payment with category tagging (AP2-approved). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice": {"type": "object", "additionalProperties": True},
                    "vendor": {"type": "string"},
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_sync_bank_fees": {
        "type": "function",
        "function": {
            "name": "finance_sync_bank_fees",
            "description": "Reconcile bank fees against an account (AP2-approved). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string"},
                    "fee_amount": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_generate_finance_report": {
        "type": "function",
        "function": {
            "name": "finance_generate_finance_report",
            "description": (
                "Generate a real P&L report from a list of transactions. "
                "Computes total_income, total_expenses, net_profit, profit_margin, "
                "expense_breakdown by description prefix, monthly_breakdown, and top 5 expenses. "
                "Pass an empty or omitted transactions list to receive a zero-value template."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transactions": {
                        "type": "array",
                        "description": (
                            "List of transaction objects. Each must have: "
                            "date (ISO string), description (string), amount (number), "
                            "type ('income' | 'expense' | 'transfer')."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string"},
                                "description": {"type": "string"},
                                "amount": {"type": "number"},
                                "type": {"type": "string", "enum": ["income", "expense", "transfer"]},
                            },
                            "required": ["date", "description", "amount", "type"],
                        },
                    },
                    "period": {"type": "string", "default": "current", "description": "Label for the report period."},
                    "currency": {"type": "string", "default": "USD", "description": "ISO 4217 currency code."},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_run_finance_close": {
        "type": "function",
        "function": {
            "name": "finance_run_finance_close",
            "description": "Full monthly close: payroll + vendor + fees + report. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_count": {"type": "integer"},
                    "cost_per_employee": {"type": "number"},
                    "vendor_amount": {"type": "number"},
                    "category": {"type": "string"},
                    "bank_fee": {"type": "number"},
                    "period": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_import_x402_transactions": {
        "type": "function",
        "function": {
            "name": "finance_import_x402_transactions",
            "description": "Bulk-import x402 ledger entries into the finance audit trail. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transactions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                },
                "additionalProperties": True,
            },
        },
    },
    "finance_get_budget_metrics": {
        "type": "function",
        "function": {
            "name": "finance_get_budget_metrics",
            "description": "Return monthly_limit, monthly_spend, remaining_budget, window. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "finance_get_audit_log": {
        "type": "function",
        "function": {
            "name": "finance_get_audit_log",
            "description": "Return signed finance audit log entries. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
    "finance_get_alerts": {
        "type": "function",
        "function": {
            "name": "finance_get_alerts",
            "description": "Return per-transaction alerts crossed this session. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
}


def register() -> None:
    register_tool("finance_run_payroll_batch", finance_run_payroll_batch, _SCHEMAS["finance_run_payroll_batch"])
    register_tool("finance_process_vendor_invoice", finance_process_vendor_invoice, _SCHEMAS["finance_process_vendor_invoice"])
    register_tool("finance_sync_bank_fees", finance_sync_bank_fees, _SCHEMAS["finance_sync_bank_fees"])
    register_tool("finance_generate_finance_report", finance_generate_finance_report, _SCHEMAS["finance_generate_finance_report"])
    register_tool("finance_run_finance_close", finance_run_finance_close, _SCHEMAS["finance_run_finance_close"])
    register_tool("finance_import_x402_transactions", finance_import_x402_transactions, _SCHEMAS["finance_import_x402_transactions"])
    register_tool("finance_get_budget_metrics", finance_get_budget_metrics, _SCHEMAS["finance_get_budget_metrics"])
    register_tool("finance_get_audit_log", finance_get_audit_log, _SCHEMAS["finance_get_audit_log"])
    register_tool("finance_get_alerts", finance_get_alerts, _SCHEMAS["finance_get_alerts"])
