"""Tool security boundary enforcement for Genesis agent runtime.

Risk classes (from least to most privileged):
  read_only         — deterministic, no side effects
  filesystem_write  — writes local files in the workspace
  network           — outbound HTTP/fetch
  browser           — browser automation (Conduit/Patchright)
  shell             — arbitrary shell execution in workspace
  subagent          — spawns another Genesis agent
  deployment        — pushes to external hosting (Vercel, Netlify, etc.)
  payment           — financial operations
  admin             — system configuration, infrastructure changes
"""
from __future__ import annotations

# Risk class constants
RISK_READ_ONLY = "read_only"
RISK_FILESYSTEM_WRITE = "filesystem_write"
RISK_NETWORK = "network"
RISK_BROWSER = "browser"
RISK_SHELL = "shell"
RISK_SUBAGENT = "subagent"
RISK_DEPLOYMENT = "deployment"
RISK_PAYMENT = "payment"
RISK_ADMIN = "admin"

# Per-tool risk class assignments
# Unknown tools default to RISK_ADMIN (fail-closed).
TOOL_RISK: dict[str, str] = {
    "file_write": RISK_FILESYSTEM_WRITE,
    "code_format": RISK_READ_ONLY,
    "genesis_call": RISK_SUBAGENT,
    "conduit": RISK_BROWSER,
    "workspace_shell": RISK_SHELL,
    "web_search": RISK_NETWORK,
    "web_fetch": RISK_NETWORK,
    "web": RISK_NETWORK,
    "github": RISK_NETWORK,
    "vercel_deploy": RISK_DEPLOYMENT,
    "netlify_deploy": RISK_DEPLOYMENT,
    "deploy": RISK_DEPLOYMENT,
    "domain": RISK_DEPLOYMENT,
    "finance": RISK_PAYMENT,
    "billing": RISK_PAYMENT,
    "commerce": RISK_PAYMENT,
    "email": RISK_NETWORK,
    "vision": RISK_NETWORK,
    "data_pipeline": RISK_FILESYSTEM_WRITE,
    "sandbox": RISK_ADMIN,
    "hr": RISK_ADMIN,
    "pricing": RISK_READ_ONLY,
    "workflow": RISK_ADMIN,
}

# Per-slug allowed risk sets
# An agent may use a tool only if the tool's risk class appears in its allowed set.
SLUG_ALLOWED_RISKS: dict[str, frozenset[str]] = {
    "genesis-meta": frozenset(
        {RISK_READ_ONLY, RISK_FILESYSTEM_WRITE, RISK_SUBAGENT, RISK_BROWSER}
    ),
    "genesis-builder": frozenset(
        {
            RISK_READ_ONLY,
            RISK_FILESYSTEM_WRITE,
            RISK_SHELL,
            RISK_BROWSER,
            RISK_DEPLOYMENT,
            RISK_NETWORK,
        }
    ),
    "genesis-research": frozenset({RISK_READ_ONLY, RISK_NETWORK}),
    "genesis-finance": frozenset({RISK_READ_ONLY, RISK_NETWORK, RISK_PAYMENT}),
    "genesis-deploy": frozenset(
        {
            RISK_READ_ONLY,
            RISK_FILESYSTEM_WRITE,
            RISK_SHELL,
            RISK_DEPLOYMENT,
            RISK_NETWORK,
        }
    ),
    "genesis-qa": frozenset(
        {
            RISK_READ_ONLY,
            RISK_FILESYSTEM_WRITE,
            RISK_SHELL,
            RISK_BROWSER,
            RISK_NETWORK,
        }
    ),
}

# Agents not in SLUG_ALLOWED_RISKS get only read_only access (fail-closed default).
DEFAULT_ALLOWED_RISKS: frozenset[str] = frozenset({RISK_READ_ONLY})


def get_tool_risk(tool_name: str) -> str:
    """Return the risk class for tool_name. Unknown tools return RISK_ADMIN (fail-closed)."""
    return TOOL_RISK.get(tool_name, RISK_ADMIN)


def is_tool_allowed(agent_slug: str, tool_name: str) -> bool:
    """Return True if agent_slug is permitted to call tool_name."""
    risk = get_tool_risk(tool_name)
    allowed = SLUG_ALLOWED_RISKS.get(agent_slug, DEFAULT_ALLOWED_RISKS)
    return risk in allowed


def check_tool_policy(agent_slug: str, tool_name: str) -> dict:
    """Return a policy result dict. ok=False means the tool call should be blocked."""
    risk = get_tool_risk(tool_name)
    allowed = SLUG_ALLOWED_RISKS.get(agent_slug, DEFAULT_ALLOWED_RISKS)
    ok = risk in allowed
    return {
        "ok": ok,
        "tool_name": tool_name,
        "agent_slug": agent_slug,
        "risk_class": risk,
        "allowed_risks": sorted(allowed),
        "error": None if ok else "tool_policy_denied",
    }
