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

import hashlib
import json
from pathlib import Path

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

# Added by docs/FINANCE-TOOL-CONTRACTS.md Section 2.4. No slug may hold it and
# no tool may be dispatched with it. assert_prohibitions_intact() enforces both.
RISK_PROHIBITED = "prohibited"

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


# ---------------------------------------------------------------------------
# PERMANENTLY_PROHIBITED enforcement
# docs/FINANCE-TOOL-CONTRACTS.md Sections 6.1 and 6.2
#
# Governing rule: automation may PREPARE, a human PAYS, automation RECORDS.
#
# Enforcement is layered so that no single edit can weaken it:
#   Layer 1  Deletion — the function bodies, schemas and register_tool lines are
#            gone from tools/*.py. Absence beats denial.
#   Layer 2  assert_prohibitions_intact() — called at gateway startup BEFORE the
#            app accepts traffic. A re-registered prohibited tool is a process
#            that refuses to start, not a request that gets denied.
#   Layer 3  Frozen manifest — runtime/prohibited_tools.sha256. Editing the list
#            below alone breaks the boot; the editor must also regenerate a hash
#            in a file named for what they are weakening.
#   Layer 4  Dispatcher pre-check in agent_runtime.py, independent of TOOL_RISK,
#            so a mistake in the risk table cannot reach a prohibited tool.
#   Layer 5  tests/test_prohibited_tools.py, including a negative control.
#   Layer 6  Gateway 403 before any LLM call, so a prohibited name never enters
#            a prompt.
# ---------------------------------------------------------------------------

# Group A — constructs or transmits a payment, transfer, ACH, wire, payroll
# disbursement or escrow settlement, or alters bank/wire instructions.
# Group B — constructs the amount of a disbursement.
# Group C — fabricates financial figures and returns them as verified success.
# All three groups are enforced identically. The grouping records WHY, so a
# future reviewer cannot argue Group C is "only a reporting bug".
PROHIBITION_GROUPS: dict[str, str] = {
    # Group A — registered tools, now deleted from the source tree
    "finance_run_payroll_batch": "A",
    "finance_process_vendor_invoice": "A",
    "finance_run_finance_close": "A",
    "billing_run_dunning_batch": "A",
    "billing_run_billing_cycle": "A",
    "commerce_register_domain": "A",
    "commerce_activate_payment_gateway": "A",
    "commerce_ship_fulfillment_batch": "A",
    "commerce_launch_commerce_stack": "A",
    "pricing_purchase_dataset": "A",
    "pricing_run_pricing_cycle": "A",
    "domain_create_intent_mandate": "A",
    "domain_register": "A",
    "domain_select_and_register": "A",
    # Group A — module functions in escrow_client.py, never registered as tools
    "escrow_client.initiate_escrow": "A",
    "escrow_client.complete_escrow": "A",
    "escrow_client.release_escrow": "A",
    # Group B
    "escrow_client.calculate_split": "B",
    # Group C
    "pricing_generate_pricing_report": "C",
    # Slug-scoped — see PROHIBITED_TOOLS_BY_SLUG. This name stays registered
    # because it is legitimate outside a finance context; it is prohibited for
    # every finance-domain slug and for any dispatch carrying a Cato
    # authorization. It is deliberately NOT in PROHIBITED_TOOLS, whose members
    # must be absent from the registry entirely.
    "workflow_webhook_trigger": "A",
}

# Slug-scoped prohibitions are excluded from the global set: the global set is
# an ABSENCE assertion and workflow_webhook_trigger is legitimately registered.
_SLUG_SCOPED_ONLY: frozenset[str] = frozenset({"workflow_webhook_trigger"})

PROHIBITED_TOOLS: frozenset[str] = frozenset(
    name for name in PROHIBITION_GROUPS if name not in _SLUG_SCOPED_ONLY
)

PROHIBITED_TOOLS_BY_SLUG: dict[str, frozenset[str]] = {
    "genesis-finance": frozenset({"workflow_webhook_trigger"}),
    "genesis-billing": frozenset({"workflow_webhook_trigger"}),
    "genesis-commerce": frozenset({"workflow_webhook_trigger"}),
    "genesis-pricing": frozenset({"workflow_webhook_trigger"}),
}

# The manifest covers every prohibited name, slug-scoped ones included, so
# removing a slug-scoped entry also breaks the hash.
PROHIBITION_MANIFEST_NAMES: tuple[str, ...] = tuple(sorted(PROHIBITION_GROUPS))

_MANIFEST_PATH = Path(__file__).parent / "prohibited_tools.sha256"


def prohibition_manifest_digest() -> str:
    """sha256 over the canonical sorted list of every prohibited name."""
    canonical = json.dumps(list(PROHIBITION_MANIFEST_NAMES), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_manifest_digest() -> str | None:
    try:
        for line in _MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line.split()[0].lower()
    except OSError:
        return None
    return None


def is_prohibited(tool_name: str, agent_slug: str | None = None) -> bool:
    """True if tool_name is prohibited outright, or prohibited for agent_slug."""
    if tool_name in PROHIBITED_TOOLS:
        return True
    if agent_slug and tool_name in PROHIBITED_TOOLS_BY_SLUG.get(agent_slug, frozenset()):
        return True
    return False


def prohibition_group(tool_name: str) -> str:
    return PROHIBITION_GROUPS.get(tool_name, "A")


def assert_prohibitions_intact(registry: dict | None = None) -> None:
    """Raise at boot if any prohibition has been weakened.

    Fail-to-boot beats fail-to-deny: a denial can be missed in logs; a service
    that will not start cannot be.

    ``registry`` exists so the negative control in tests/test_prohibited_tools.py
    can prove this function actually raises. Production callers pass nothing and
    the live tools registry is inspected.
    """
    # Layer 3 — frozen manifest. Editing the list without regenerating the hash
    # breaks the boot, forcing a two-file, self-documenting, reviewable change.
    expected = prohibition_manifest_digest()
    on_disk = _read_manifest_digest()
    if on_disk is None:
        raise RuntimeError(
            f"prohibition manifest missing or unreadable: {_MANIFEST_PATH}. "
            "Refusing to start: the prohibited-tool list cannot be verified."
        )
    if on_disk != expected:
        raise RuntimeError(
            "prohibition manifest mismatch: the PERMANENTLY_PROHIBITED list has "
            f"been edited without regenerating {_MANIFEST_PATH.name}. "
            f"expected={expected} on_disk={on_disk}. "
            "Regenerate with: python scripts/regen_prohibited_manifest.py"
        )

    # Layer 2 — absence assertion over the live registry.
    if registry is None:
        import tools  # imported lazily so this module stays importable standalone
        registry = tools._TOOLS
    present = sorted(PROHIBITED_TOOLS & set(registry))
    if present:
        raise RuntimeError(
            f"prohibited tools are registered: {present}. "
            "These operations construct or transmit money, or fabricate financial "
            "figures, and must not exist as callable tools. "
            "See docs/FINANCE-TOOL-CONTRACTS.md Section 6."
        )

    # No slug may hold the prohibited risk class.
    for slug, allowed in SLUG_ALLOWED_RISKS.items():
        if RISK_PROHIBITED in allowed:
            raise RuntimeError(f"slug {slug} grants RISK_PROHIBITED")
    if RISK_PROHIBITED in DEFAULT_ALLOWED_RISKS:
        raise RuntimeError("DEFAULT_ALLOWED_RISKS grants RISK_PROHIBITED")


def get_tool_risk(tool_name: str) -> str:
    """Return the risk class for tool_name. Unknown tools return RISK_ADMIN (fail-closed)."""
    if tool_name in PROHIBITED_TOOLS:
        return RISK_PROHIBITED
    return TOOL_RISK.get(tool_name, RISK_ADMIN)


def is_tool_allowed(agent_slug: str, tool_name: str) -> bool:
    """Return True if agent_slug is permitted to call tool_name."""
    risk = get_tool_risk(tool_name)
    allowed = SLUG_ALLOWED_RISKS.get(agent_slug, DEFAULT_ALLOWED_RISKS)
    return risk in allowed


def check_tool_policy(agent_slug: str, tool_name: str) -> dict:
    """Return a policy result dict. ok=False means the tool call should be blocked."""
    # Prohibition is evaluated first and is independent of TOOL_RISK and
    # SLUG_ALLOWED_RISKS, so a mistake in the risk table cannot reach a
    # prohibited tool. A denial here is not overridable by configuration.
    if is_prohibited(tool_name, agent_slug):
        return {
            "ok": False,
            "tool_name": tool_name,
            "agent_slug": agent_slug,
            "risk_class": RISK_PROHIBITED,
            "allowed_risks": sorted(SLUG_ALLOWED_RISKS.get(agent_slug, DEFAULT_ALLOWED_RISKS)),
            "prohibition_group": prohibition_group(tool_name),
            "error": "tool_policy_denied",
        }
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
