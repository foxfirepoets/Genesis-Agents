"""Genesis Domain tools - Phase 3 scaffolds + functional candidate generator.

Wraps the operations advertised by skill_bundles/genesis-domain.json so the
agent runtime can dispatch them without 500s. The candidate generator is
fully functional; the availability check calls Name.com's REST API when
NAMECOM_USERNAME + NAMECOM_TOKEN are present in env, otherwise returns a
scaffold response. Registration, DNS, and AP2 mandate flows are scaffolds
for Phase 9.
"""
from __future__ import annotations

import logging
import os
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
    log.exception("domain tool %s failed", action)
    return {
        "ok": False,
        "action": action,
        "error": type(exc).__name__,
        "message": str(exc),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def domain_generate_candidates(
    *,
    theme: str | None = None,
    business_name: str | None = None,
    business_type: str | None = None,
    count: int = 10,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate scored domain-name candidates around a theme / business name.

    Heuristic: shorter root scores higher; hyphens penalised; popular TLDs
    (.com, .io) get a bonus. Deduplicated and sorted descending by score.
    """
    try:
        root_theme = (theme or business_name or "").strip().lower()
        if not root_theme:
            return {
                "ok": False,
                "error": "missing_input",
                "message": "Provide 'theme' or 'business_name'.",
            }
        # Strip non-alphanumeric chars from the root.
        cleaned = "".join(ch for ch in root_theme if ch.isalnum())
        if not cleaned:
            return {
                "ok": False,
                "error": "invalid_input",
                "message": "Theme/business_name had no alphanumeric characters.",
            }

        prefixes = ["", "get", "my", "the", "use"]
        suffixes = ["", "hq", "io", "app", "ai", "co"]
        tlds = [".com", ".io", ".ai", ".co", ".dev", ".app"]

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in prefixes:
            for s in suffixes:
                for tld in tlds:
                    root = f"{p}{cleaned}{s}"
                    domain = f"{root}{tld}"
                    if domain in seen:
                        continue
                    seen.add(domain)
                    score = 100 - len(root) - (10 if "-" in root else 0)
                    if tld in (".com", ".io"):
                        score += 5
                    candidates.append({
                        "domain": domain,
                        "score": score,
                        "tld": tld,
                        "length": len(root),
                        "memorable": len(root) <= 12,
                        "brandable": p == "" and s == "",
                    })
        candidates.sort(key=lambda c: -c["score"])
        top = candidates[: max(1, int(count))]
        return {
            "ok": True,
            "action": "domain_generate_candidates",
            "theme": root_theme,
            "count": len(top),
            "candidates": top,
        }
    except Exception as e:
        return _err("domain_generate_candidates", e)


async def domain_check_availability(
    *,
    domains: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Check availability via Name.com if NAMECOM_USERNAME + NAMECOM_TOKEN are
    set in env, else return a scaffold response.
    """
    try:
        domain_list = domains or []
        if not domain_list:
            return {
                "ok": False,
                "error": "missing_input",
                "message": "Provide 'domains' (non-empty list of strings).",
            }

        username = os.getenv("NAMECOM_USERNAME")
        token = os.getenv("NAMECOM_TOKEN")
        if not (username and token):
            return {
                "ok": True,
                "stub": True,
                "action": "domain_check_availability",
                "results": [
                    {"domain": d, "available": None, "premium": None, "price_usd": None}
                    for d in domain_list
                ],
                "note": (
                    "NAMECOM credentials not configured - returning stub. "
                    "Set NAMECOM_USERNAME and NAMECOM_TOKEN to enable real checks."
                ),
            }

        try:
            import httpx  # type: ignore
        except Exception as imp_err:
            return {
                "ok": False,
                "error": "httpx_not_installed",
                "message": f"httpx import failed: {imp_err}",
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.name.com/v4/domains:checkAvailability",
                    auth=(username, token),
                    json={"domainNames": domain_list},
                )
                data = resp.json()
                return {
                    "ok": resp.status_code < 400,
                    "action": "domain_check_availability",
                    "status_code": resp.status_code,
                    "results": data.get("results", []),
                }
        except Exception as e:
            return {
                "ok": False,
                "action": "domain_check_availability",
                "error": type(e).__name__,
                "message": str(e),
            }
    except Exception as e:
        return _err("domain_check_availability", e)


async def domain_create_intent_mandate(
    *,
    user_id: str | None = None,
    business_name: str | None = None,
    business_type: str | None = None,
    max_domains: int | None = None,
    max_price_per_domain: float | None = None,
    valid_for_hours: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "user_id": user_id,
            "business_name": business_name,
            "business_type": business_type,
            "max_domains": max_domains,
            "max_price_per_domain": max_price_per_domain,
            "valid_for_hours": valid_for_hours,
        }
        return _scaffold(
            "domain_create_intent_mandate",
            args,
            extra={
                "intent_mandate_id": f"intent_{uuid.uuid4().hex[:12]}",
                "status": "pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("domain_create_intent_mandate", e)


async def domain_register(
    *,
    domain: str | None = None,
    buyer_consent_token: str | None = None,
    years: int = 1,
    privacy: bool = True,
    auto_renew: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "domain": domain,
            "buyer_consent_token": buyer_consent_token,
            "years": years,
            "privacy": privacy,
            "auto_renew": auto_renew,
        }
        return _scaffold(
            "domain_register",
            args,
            extra={
                "registration_id": f"reg_{uuid.uuid4().hex[:12]}",
                "domain": domain,
                "status": "pending_ap2_approval",
            },
        )
    except Exception as e:
        return _err("domain_register", e)


async def domain_configure_dns(
    *,
    domain: str | None = None,
    records: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {"domain": domain, "records": records}
        return _scaffold(
            "domain_configure_dns",
            args,
            extra={
                "config_id": f"dns_{uuid.uuid4().hex[:12]}",
                "records_count": len(records or []),
                "status": "configured",
            },
        )
    except Exception as e:
        return _err("domain_configure_dns", e)


async def domain_select_and_register(
    *,
    business_name: str | None = None,
    business_type: str | None = None,
    user_id: str | None = None,
    auto_register: bool = False,
    configure_dns: bool = False,
    max_cost: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        args = {
            "business_name": business_name,
            "business_type": business_type,
            "user_id": user_id,
            "auto_register": auto_register,
            "configure_dns": configure_dns,
            "max_cost": max_cost,
        }
        return _scaffold(
            "domain_select_and_register",
            args,
            extra={
                "workflow_id": f"dwf_{uuid.uuid4().hex[:12]}",
                "stages": [
                    "candidates_generated",
                    "availability_checked",
                    "intent_mandate_created",
                    "domain_registered",
                    "dns_configured",
                ],
                "status": "scaffold_complete",
            },
        )
    except Exception as e:
        return _err("domain_select_and_register", e)


async def domain_get_cost_summary(**kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "stub": True,
            "action": "domain_get_cost_summary",
            "total_monthly_cost": 0.00,
            "total_domains": 0,
            "threshold_exceeded": False,
            "registered_domains": [],
            "note": "Phase 3 scaffold - real AP2 metrics in Phase 6",
        }
    except Exception as e:
        return _err("domain_get_cost_summary", e)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict[str, Any]] = {
    "domain_generate_candidates": {
        "type": "function",
        "function": {
            "name": "domain_generate_candidates",
            "description": (
                "Generate scored domain-name candidates around a theme or business name. "
                "Returns a ranked list with score/tld/length/memorable/brandable per candidate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "description": "Theme or seed root for candidates."},
                    "business_name": {"type": "string", "description": "Business name (alternate to theme)."},
                    "business_type": {"type": "string", "description": "Business type / industry hint."},
                    "count": {"type": "integer", "default": 10},
                },
                "additionalProperties": True,
            },
        },
    },
    "domain_check_availability": {
        "type": "function",
        "function": {
            "name": "domain_check_availability",
            "description": (
                "Batch-check domain availability via Name.com when NAMECOM_USERNAME+NAMECOM_TOKEN "
                "env vars are set; returns a scaffold response otherwise."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of fully-qualified domain names to check.",
                    },
                },
                "required": ["domains"],
                "additionalProperties": True,
            },
        },
    },
    "domain_create_intent_mandate": {
        "type": "function",
        "function": {
            "name": "domain_create_intent_mandate",
            "description": "Create an AP2 IntentMandate authorizing N domain purchases under $X. Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "business_name": {"type": "string"},
                    "business_type": {"type": "string"},
                    "max_domains": {"type": "integer"},
                    "max_price_per_domain": {"type": "number"},
                    "valid_for_hours": {"type": "integer"},
                },
                "additionalProperties": True,
            },
        },
    },
    "domain_register": {
        "type": "function",
        "function": {
            "name": "domain_register",
            "description": "Register a specific domain via the registrar (AP2 cart-mandate-gated). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "buyer_consent_token": {"type": "string"},
                    "years": {"type": "integer", "default": 1},
                    "privacy": {"type": "boolean", "default": True},
                    "auto_renew": {"type": "boolean", "default": True},
                },
                "required": ["domain"],
                "additionalProperties": True,
            },
        },
    },
    "domain_configure_dns": {
        "type": "function",
        "function": {
            "name": "domain_configure_dns",
            "description": "Write DNS records for a domain (e.g. GitHub Pages CNAME/A). Phase 3 scaffold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "records": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                },
                "required": ["domain"],
                "additionalProperties": True,
            },
        },
    },
    "domain_select_and_register": {
        "type": "function",
        "function": {
            "name": "domain_select_and_register",
            "description": (
                "End-to-end workflow: generate candidates, check availability, create AP2 mandate, "
                "register, and optionally configure DNS. Phase 3 scaffold."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "business_name": {"type": "string"},
                    "business_type": {"type": "string"},
                    "user_id": {"type": "string"},
                    "auto_register": {"type": "boolean", "default": False},
                    "configure_dns": {"type": "boolean", "default": False},
                    "max_cost": {"type": "number"},
                },
                "additionalProperties": True,
            },
        },
    },
    "domain_get_cost_summary": {
        "type": "function",
        "function": {
            "name": "domain_get_cost_summary",
            "description": "Return total_monthly_cost, total_domains, threshold_exceeded, registered_domains. Phase 3 scaffold.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    },
}


def register() -> None:
    register_tool("domain_generate_candidates", domain_generate_candidates, _SCHEMAS["domain_generate_candidates"])
    register_tool("domain_check_availability", domain_check_availability, _SCHEMAS["domain_check_availability"])
    register_tool("domain_create_intent_mandate", domain_create_intent_mandate, _SCHEMAS["domain_create_intent_mandate"])
    register_tool("domain_register", domain_register, _SCHEMAS["domain_register"])
    register_tool("domain_configure_dns", domain_configure_dns, _SCHEMAS["domain_configure_dns"])
    register_tool("domain_select_and_register", domain_select_and_register, _SCHEMAS["domain_select_and_register"])
    register_tool("domain_get_cost_summary", domain_get_cost_summary, _SCHEMAS["domain_get_cost_summary"])
