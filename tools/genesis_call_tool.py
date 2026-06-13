"""genesis_call - internal agent-to-agent dispatch for the meta orchestrator."""
from __future__ import annotations
import logging
import uuid
from typing import Any

from . import register_tool

log = logging.getLogger(__name__)


async def genesis_call(
    *,
    agent: str,
    task: str,
    params: dict[str, Any] | None = None,
    _runtime: Any = None,
    _parent_job_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch to another Genesis agent. _runtime is injected by the caller's agent_runtime instance."""
    if _runtime is None:
        return {
            "ok": False,
            "error": "no_runtime_in_context",
            "target_agent_slug": agent,
        }

    child_job_id = f"child-{uuid.uuid4().hex[:12]}"
    try:
        result = await _runtime.execute_agent(agent, task, params or {}, job_id=child_job_id)
        child_ok = bool(result.get("ok"))
        child_response = str(result.get("response", ""))
        return {
            "ok": True,
            "target_agent_slug": agent,
            "child_job_id": child_job_id,
            "child_ok": child_ok,
            "child_response_summary": child_response[:500],
            "child_trace": result.get("trace", {}),
            # backwards-compat aliases
            "agent": agent,
            "result": result,
        }
    except Exception as e:
        log.exception("genesis_call to %s failed", agent)
        return {
            "ok": False,
            "target_agent_slug": agent,
            "child_job_id": child_job_id,
            "error": type(e).__name__,
            "message": str(e),
            "agent": agent,
        }


GENESIS_CALL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "genesis_call",
        "description": "Dispatch a task to another Genesis agent by slug. Used by orchestrator agents to delegate specialist work.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Target agent slug, e.g. 'genesis-research', 'genesis-builder', 'genesis-qa'"},
                "task": {"type": "string", "description": "Plain-text task for that agent"},
                "params": {"type": "object", "additionalProperties": True, "description": "Optional extra parameters for the agent"},
            },
            "required": ["agent", "task"],
        },
    },
}


def register() -> None:
    register_tool("genesis_call", genesis_call, GENESIS_CALL_SCHEMA)
