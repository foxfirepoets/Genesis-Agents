"""genesis_call - internal agent-to-agent dispatch for the meta orchestrator."""
from __future__ import annotations
import logging
from typing import Any

from . import register_tool

log = logging.getLogger(__name__)


async def genesis_call(
    *,
    agent: str,
    task: str,
    params: dict[str, Any] | None = None,
    _runtime: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch to another Genesis agent. _runtime is injected by the caller's agent_runtime instance."""
    if _runtime is None:
        return {"ok": False, "error": "no_runtime_in_context"}
    try:
        result = await _runtime.execute_agent(agent, task, params or {})
        return {"ok": True, "agent": agent, "result": result}
    except Exception as e:
        log.exception("genesis_call to %s failed", agent)
        return {"ok": False, "error": type(e).__name__, "message": str(e), "agent": agent}


GENESIS_CALL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "genesis_call",
        "description": "Dispatch a task to another Genesis agent by slug. Used by orchestrator agents.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Target agent slug, e.g. 'genesis-research'"},
                "task": {"type": "string", "description": "Plain-text task for that agent"},
                "params": {"type": "object", "additionalProperties": True},
            },
            "required": ["agent", "task"],
        },
    },
}


def register() -> None:
    register_tool("genesis_call", genesis_call, GENESIS_CALL_SCHEMA)
