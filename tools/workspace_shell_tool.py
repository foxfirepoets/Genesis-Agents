"""workspace_shell — controlled shell execution inside a job workspace.

Runs commands inside /tmp/jobs/{job_id}/workspace/ with strict constraints:
- cwd must be under _job_dir
- blocked dangerous command prefixes
- timeout enforced
- output capped at 64KB
- env vars scrubbed (no inherited secrets, no leaking AWS_*/GITHUB_* etc.)
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from . import register_tool

log = logging.getLogger(__name__)

_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB
_MAX_TIMEOUT_S = 60
_DEFAULT_TIMEOUT_S = 30

# Commands that are never allowed regardless of context
_BLOCKED_PREFIXES = (
    "rm -rf /",
    "rm -rf ~",
    "dd ",
    "mkfs",
    "fdisk",
    "shutdown",
    "reboot",
    "halt",
    "kill -9 1",
    "pkill",
    "killall",
    ":(){ :|:& };:",  # fork bomb
    "curl | bash",
    "wget | bash",
    "curl | sh",
    "wget | sh",
    "> /dev/sda",
    "chmod 777 /",
    "chown root",
)

# Regex: pipe-to-shell pattern. Catches `curl URL | bash` and similar where
# a URL or args appear between the pipe and the interpreter.
_PIPE_TO_SHELL_RE = re.compile(
    r'\|\s*(bash|sh|python3?|perl|ruby|node)\b',
    re.IGNORECASE,
)

# Regex: suspicious values that look like known API-key prefixes (for env_extra values)
_SECRET_VALUE_RE = re.compile(
    r'(sk_live|sk_test|AKIA[0-9A-Z]{16}|ghp_|glpat-|xoxp-|xoxb-)',
    re.IGNORECASE,
)

# Env var name patterns to redact from inherited environment
_REDACT_PATTERNS = re.compile(
    r"(token|secret|key|password|api_key|apikey|bearer|auth|private|credential|pwd)",
    re.IGNORECASE,
)

_SAFE_ENV_PASSTHROUGH = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE", "TERM"}


def _build_safe_env(base_dir: Path) -> dict[str, str]:
    """Build a minimal environment with no secret leakage."""
    safe: dict[str, str] = {}
    for key in _SAFE_ENV_PASSTHROUGH:
        val = os.environ.get(key)
        if val:
            safe[key] = val
    safe["HOME"] = str(base_dir)
    safe["TMPDIR"] = str(base_dir / "tmp")
    return safe


def _is_blocked(cmd: str) -> bool:
    stripped = cmd.strip().lower()
    for prefix in _BLOCKED_PREFIXES:
        if stripped.startswith(prefix.lower()) or prefix.lower() in stripped:
            return True
    # Catch `curl URL | bash` and similar where a URL appears between | and interpreter.
    if _PIPE_TO_SHELL_RE.search(stripped):
        return True
    return False


def _assert_within_workspace(cwd: Path, job_dir: Path) -> None:
    """Raise ValueError if cwd escapes the job workspace."""
    try:
        cwd.resolve().relative_to(job_dir.resolve())
    except ValueError:
        raise ValueError(
            f"cwd '{cwd}' is outside the job workspace '{job_dir}'. "
            "Commands must run within the job workspace."
        )


async def workspace_shell(
    *,
    command: str,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
    _job_dir: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a shell command inside the job workspace.

    The working directory must be within _job_dir (/tmp/jobs/{job_id}/).
    Dangerous commands, secret env vars, and path escapes are all blocked.
    """
    if _job_dir is None:
        return {
            "ok": False,
            "error": "no_job_dir",
            "message": "workspace_shell requires a job context (_job_dir). Use this tool only within an active job.",
        }

    if not command or not command.strip():
        return {"ok": False, "error": "empty_command"}

    if _is_blocked(command):
        return {
            "ok": False,
            "error": "command_blocked",
            "message": f"Command is blocked by safety policy: {command[:80]}",
        }

    clamped_timeout = min(max(1, timeout), _MAX_TIMEOUT_S)

    # Resolve working directory — default to workspace subdir
    workspace_dir = _job_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (_job_dir / "tmp").mkdir(parents=True, exist_ok=True)

    if cwd:
        resolved_cwd = (workspace_dir / cwd).resolve()
    else:
        resolved_cwd = workspace_dir.resolve()

    try:
        _assert_within_workspace(resolved_cwd, _job_dir)
    except ValueError as e:
        return {"ok": False, "error": "path_escape_blocked", "message": str(e)}

    resolved_cwd.mkdir(parents=True, exist_ok=True)

    # Build environment
    safe_env = _build_safe_env(_job_dir)
    if env_extra:
        for k, v in env_extra.items():
            if not _REDACT_PATTERNS.search(k) and not _SECRET_VALUE_RE.search(str(v)):
                safe_env[k] = str(v)

    def _run_sync() -> dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(resolved_cwd),
                capture_output=True,
                timeout=clamped_timeout,
                env=safe_env,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]
            stderr = result.stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]
            return {
                "ok": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "cwd": str(resolved_cwd),
                "truncated": len(result.stdout) > _MAX_OUTPUT_BYTES or len(result.stderr) > _MAX_OUTPUT_BYTES,
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "timeout",
                "timeout_seconds": clamped_timeout,
                "message": f"Command timed out after {clamped_timeout}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }

    try:
        return await asyncio.to_thread(_run_sync)
    except Exception as exc:
        log.exception("workspace_shell failed to dispatch")
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


WORKSPACE_SHELL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "workspace_shell",
        "description": (
            f"Run a shell command inside the job workspace (/tmp/jobs/{{job_id}}/workspace/). "
            f"Max timeout: {_MAX_TIMEOUT_S}s. Max output: 64KB. "
            "Commands that escape the workspace, delete system files, or expose secrets are blocked. "
            "Use for: running tests, lint, build commands, npm install, pytest, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (bash syntax).",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory relative to workspace root (default: workspace root).",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (max {_MAX_TIMEOUT_S}, default {_DEFAULT_TIMEOUT_S}).",
                    "default": _DEFAULT_TIMEOUT_S,
                },
                "env_extra": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Additional non-secret environment variables to set.",
                },
            },
            "required": ["command"],
        },
    },
}


def register() -> None:
    register_tool("workspace_shell", workspace_shell, WORKSPACE_SHELL_SCHEMA)
