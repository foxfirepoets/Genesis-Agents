"""Genesis agent runtime - multi-turn LLM loop with tool dispatch, per-slug parameterized."""
from __future__ import annotations
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from bundle_loader import load_bundle
from tools import get_tool, tool_schemas_for, register_default_tools

log = logging.getLogger(__name__)

# Resource limits — Phase 11 sandbox enforcement.
MAX_TURNS = 10
MAX_LLM_CALLS = 10  # Same as MAX_TURNS but tracked explicitly for clarity.
MAX_TOKENS_PER_JOB = 50_000  # Aggregate over all turns (response.usage.total_tokens).
MAX_FILES_WRITTEN = 20  # Hard cap on file_write tool successes per job.
DEFAULT_TIMEOUT_S = 300  # 5 minutes wall-time.
DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024  # 4 MB per tool result.
DEFAULT_SWARMSYNC_MODEL = "minimax/minimax-m2.5"
OPENROUTER_HOST_MARKERS = ("openrouter.ai",)


def _check_success_criteria(criteria: list[dict] | None, result: dict) -> dict[str, Any]:
    """Validate result against bundle's success_criteria. Returns {ok, failed: [...]}.

    Supported criteria types:
      - non_empty           : response must be non-empty.
      - contains_keys       : response (JSON-parseable) must contain `keys`.
      - max_latency_s       : result.elapsed_s must be <= configured seconds.
    Unknown types are ignored (forward-compatible).
    """
    if not criteria:
        criteria = [{"type": "non_empty"}]
    failed: list[dict[str, Any]] = []
    for c in criteria:
        ct = c.get("type")
        if ct == "non_empty":
            if not result.get("response"):
                failed.append({"type": ct, "reason": "response is empty"})
        elif ct == "contains_keys":
            keys = (c.get("config") or {}).get("keys", [])
            try:
                response_obj = json.loads(result.get("response") or "{}")
                if not isinstance(response_obj, dict):
                    failed.append({"type": ct, "reason": "response not a JSON object"})
                else:
                    for k in keys:
                        if k not in response_obj:
                            failed.append({"type": ct, "reason": f"missing key: {k}"})
            except Exception:
                failed.append({"type": ct, "reason": "response not parseable as JSON"})
        elif ct == "max_latency_s":
            max_s = (c.get("config") or {}).get("seconds", 300)
            elapsed = result.get("elapsed_s", 0) or 0
            if elapsed > max_s:
                failed.append({
                    "type": ct,
                    "reason": f"elapsed {elapsed}s > {max_s}s",
                })
    return {"ok": len(failed) == 0, "failed": failed}

# Lazy module init
_DEFAULTS_REGISTERED = False


def _ensure_tools_registered() -> None:
    global _DEFAULTS_REGISTERED
    if not _DEFAULTS_REGISTERED:
        register_default_tools()
        _DEFAULTS_REGISTERED = True


class AgentRuntime:
    """Runs a single agent invocation."""

    def __init__(self, llm_url: str, llm_key: str):
        self.llm_url = llm_url
        self.llm_key = llm_key
        _ensure_tools_registered()

    async def execute_agent(self, slug: str, task: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute one agent invocation. Returns structured result."""
        bundle = load_bundle(slug)
        if bundle is None:
            return {"ok": False, "error": "unknown_slug", "slug": slug}

        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job_dir = Path(f"/tmp/jobs/{job_id}")
        job_dir.mkdir(parents=True, exist_ok=True)

        # Lazy-init Conduit bridge per job (only if conduit is in tools_advertised)
        bridge = None
        buyer_session: Any = None
        if "conduit" in bundle.get("tools_advertised", []):
            try:
                from conduit_browser import ConduitBridge
                bridge = ConduitBridge(
                    session_id=job_id,
                    budget_cents=bundle.get("conduit_budget_cents", 200),
                    data_dir=job_dir / "conduit",
                )
                # Phase 9b - if a buyer uploaded a Conduit session for this
                # job ("Concierge Mode"), pull it from the encrypted vault now
                # and inject it into the bridge AFTER start() (Playwright
                # context must exist before add_cookies will accept anything).
                try:
                    from conduit_sessions import load_session
                    sess_result = load_session(job_id=job_id)
                    if sess_result.get("ok") and sess_result.get("session_data"):
                        buyer_session = sess_result["session_data"]
                        log.info(
                            "loading buyer session for job %s (concierge mode)",
                            job_id,
                        )
                except Exception:
                    log.exception("session load failed; continuing without buyer session")

                await bridge.start()

                if buyer_session is not None:
                    try:
                        # Conduit's session-import API is the BrowserTool's
                        # cookie-jar label system: write the cookie array as
                        # a label file under the bridge's _session_dir, then
                        # call ConduitBridge.load_cookies(label=...) which
                        # internally invokes Playwright's
                        # `BrowserContext.add_cookies(cookies)` via
                        # BrowserTool._load_cookies. Audit event is recorded
                        # by the bridge as part of the call.
                        #
                        # Accepted buyer formats:
                        #   - Playwright storage_state dict:
                        #       {"cookies": [...], "origins": [...]}
                        #     (origins/localStorage not yet wired; cookies only.)
                        #   - Raw cookie array: [{name, value, domain, ...}, ...]
                        if isinstance(buyer_session, dict):
                            cookies_list = buyer_session.get("cookies", [])
                        elif isinstance(buyer_session, list):
                            cookies_list = buyer_session
                        else:
                            cookies_list = []

                        if cookies_list:
                            browser_tool = getattr(bridge, "_browser_tool", None)
                            if browser_tool is None or getattr(browser_tool, "_session_dir", None) is None:
                                raise RuntimeError("bridge._browser_tool not initialised after start()")
                            label = "buyer"
                            session_file = browser_tool._session_dir / f"{label}.json"
                            session_file.parent.mkdir(parents=True, exist_ok=True)
                            session_file.write_text(
                                json.dumps(cookies_list), encoding="utf-8"
                            )
                            inject_result = await bridge.load_cookies(label=label)
                            if not (inject_result or {}).get("success"):
                                raise RuntimeError(
                                    f"load_cookies returned non-success: {inject_result}"
                                )
                            log.info(
                                "buyer session injected into bridge for job %s (cookies=%d)",
                                job_id,
                                inject_result.get("count", len(cookies_list)),
                            )
                        else:
                            log.warning(
                                "buyer session for job %s had no cookies; nothing injected",
                                job_id,
                            )
                    except Exception:
                        log.exception(
                            "buyer session injection failed for job %s; continuing without",
                            job_id,
                        )
            except Exception:
                log.exception("ConduitBridge failed to start for %s", slug)
                bridge = None

        try:
            return await self._run_loop(bundle, task, params, job_id, job_dir, bridge)
        finally:
            if bridge is not None:
                try:
                    await bridge.stop()
                except Exception:
                    log.warning("bridge.stop() failed for %s", job_id)
            # Concierge cleanup: delete buyer session from vault after job
            # completion so credentials don't accumulate on disk. Best-effort.
            try:
                from conduit_sessions import delete_session
                delete_session(job_id=job_id)
            except Exception:
                log.warning("session cleanup failed for job %s", job_id)

    async def _run_loop(
        self,
        bundle: dict[str, Any],
        task: str,
        params: dict[str, Any],
        job_id: str,
        job_dir: Path,
        bridge: Any,
    ) -> dict[str, Any]:
        slug = bundle["slug"]
        last_swarmsync: dict[str, Any] | None = None
        tools_advertised = bundle.get("tools_advertised", [])
        token_budget = bundle.get("token_budget", 4000)
        model = bundle.get("model_hint", "anthropic/claude-sonnet-4-5")
        timeout_s = bundle.get("timeout_s", DEFAULT_TIMEOUT_S)

        system_prompt = bundle["system_prompt"]
        user_prompt = task + (f"\n\nAdditional params: {json.dumps(params)}" if params else "")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tools = tool_schemas_for(tools_advertised)

        started = time.time()
        turn = 0
        llm_calls = 0
        total_tokens = 0
        files_written = 0
        success_criteria = bundle.get("success_criteria")

        while turn < MAX_TURNS:
            turn += 1
            if time.time() - started > timeout_s:
                return {
                    "ok": False,
                    "error": "timeout",
                    "slug": slug,
                    "turns_completed": turn - 1,
                }

            # Phase 11 — enforce LLM call cap (parallel to MAX_TURNS, makes
            # the limit explicit and easier to audit).
            if llm_calls >= MAX_LLM_CALLS:
                return {
                    "ok": False,
                    "error": "llm_call_limit_exceeded",
                    "slug": slug,
                    "llm_calls": llm_calls,
                    "limit": MAX_LLM_CALLS,
                }

            # Call LLM
            try:
                response = await self._call_llm(model, messages, tools, token_budget)
                llm_calls += 1
                if isinstance(response.get("swarmsync"), dict):
                    last_swarmsync = response["swarmsync"]
            except Exception as e:
                log.exception("LLM call failed turn=%d slug=%s", turn, slug)
                return {
                    "ok": False,
                    "error": "llm_call_failed",
                    "type": type(e).__name__,
                    "message": str(e),
                }

            # Phase 11 — aggregate token-budget enforcement.
            try:
                usage = response.get("usage") or {}
                total_tokens += int(usage.get("total_tokens", 0) or 0)
            except Exception:
                pass
            if total_tokens > MAX_TOKENS_PER_JOB:
                return {
                    "ok": False,
                    "error": "token_budget_exceeded",
                    "slug": slug,
                    "total_tokens": total_tokens,
                    "limit": MAX_TOKENS_PER_JOB,
                }

            # Parse response - OpenAI-format expected
            choices = response.get("choices", [])
            if not choices:
                return {"ok": False, "error": "no_choices_in_llm_response"}

            msg = choices[0].get("message", {})
            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content")

            if not tool_calls:
                # Final answer
                result: dict[str, Any] = {
                    "ok": True,
                    "slug": slug,
                    "response": content,
                    "turns": turn,
                    "elapsed_s": round(time.time() - started, 2),
                    "job_id": job_id,
                    "resource_usage": {
                        "llm_calls": llm_calls,
                        "total_tokens": total_tokens,
                        "files_written": files_written,
                    },
                }
                if last_swarmsync:
                    result["swarmsync"] = last_swarmsync
                    routed = last_swarmsync.get("routed_model") or ""
                    result["routing"] = {
                        "model": routed,
                        "provider": routed.split("/")[0] if "/" in routed else routed,
                        "tier": last_swarmsync.get("tier"),
                        "routing_reason": last_swarmsync.get("routing_reason"),
                        "estimated_cost": last_swarmsync.get("estimated_cost"),
                        "latency_ms": last_swarmsync.get("latency_ms"),
                    }

                # Phase 11 — validate success_criteria against the structured
                # result. If any fail, mark the job FAILED so the worker can
                # refund escrow (Phase 6) and reputation tracking updates.
                criteria_eval = _check_success_criteria(success_criteria, result)
                result["success_criteria_eval"] = criteria_eval
                if not criteria_eval["ok"]:
                    result["ok"] = False
                    result["error"] = "success_criteria_failed"

                # Phase 7 — generate VCAP proof bundle if we have a Conduit bridge
                if bridge is not None:
                    try:
                        from proof_bridge import generate_proof_for_job
                        proof = await generate_proof_for_job(
                            job_id=job_id,
                            agent_slug=slug,
                            bridge=bridge,
                            job_dir=job_dir,
                            input_data={"task": task, "params": params},
                            output_data={"response": content, "turns": turn},
                            started_at=started,
                            completed_at=time.time(),
                        )
                        if proof.get("ok"):
                            result["proof"] = {
                                "proof_id": proof.get("proof_id"),
                                "vcap_wrapper_jwt": proof.get("vcap_wrapper_jwt"),
                                "proof_bundle_signed_url": proof.get("signed_url"),
                                "input_hash": proof.get("input_hash"),
                                "output_hash": proof.get("output_hash"),
                            }
                        else:
                            result["proof"] = {
                                "ok": False,
                                "error": proof.get("error"),
                            }
                    except Exception:
                        log.exception("proof generation raised; continuing without proof")
                        result["proof"] = {
                            "ok": False,
                            "error": "proof_pipeline_exception",
                        }

                return result

            # Append the assistant message to history
            messages.append(msg)

            # Execute each tool call
            for tc in tool_calls:
                tc_id = tc.get("id", "unknown")
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}

                tool = get_tool(fn_name)
                if tool is None or fn_name not in tools_advertised:
                    tool_result: dict[str, Any] = {
                        "ok": False,
                        "error": "tool_not_allowed",
                        "tool": fn_name,
                    }
                else:
                    # Phase 11 — file_write quota enforced BEFORE the call.
                    if fn_name == "file_write" and files_written >= MAX_FILES_WRITTEN:
                        tool_result = {
                            "ok": False,
                            "error": "file_write_limit_exceeded",
                            "files_written": files_written,
                            "limit": MAX_FILES_WRITTEN,
                        }
                    else:
                        # Inject context: bridge, job_dir, runtime
                        ctx = {"_bridge": bridge, "_job_dir": job_dir, "_runtime": self}
                        try:
                            tool_result = await tool(**args, **ctx)
                            # Phase 11 — count successful file writes.
                            if (
                                fn_name == "file_write"
                                and isinstance(tool_result, dict)
                                and tool_result.get("ok")
                            ):
                                files_written += 1
                        except Exception as e:
                            log.exception("tool %s raised", fn_name)
                            tool_result = {
                                "ok": False,
                                "error": "tool_exception",
                                "type": type(e).__name__,
                                "message": str(e),
                            }

                # Append tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": json.dumps(tool_result)[:DEFAULT_MAX_OUTPUT_BYTES],
                })

        return {
            "ok": False,
            "error": "max_turns_reached",
            "slug": slug,
            "turns": turn,
            "resource_usage": {
                "llm_calls": llm_calls,
                "total_tokens": total_tokens,
                "files_written": files_written,
            },
        }

    async def _call_llm(
        self,
        model: str,
        messages: list,
        tools: list,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call the configured LLM endpoint. OpenAI-format request/response."""
        import aiohttp

        allow_openrouter_fallback = os.getenv("GENESIS_ALLOW_OPENROUTER_FALLBACK", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if any(marker in self.llm_url for marker in OPENROUTER_HOST_MARKERS) and not allow_openrouter_fallback:
            raise RuntimeError(
                "OpenRouter is disabled for Genesis agents; set LLM_API_URL to "
                "https://api.swarmsync.ai/v1/chat/completions or explicitly enable "
                "GENESIS_ALLOW_OPENROUTER_FALLBACK=true"
            )

        primary = (os.getenv("GENESIS_LLM_MODEL") or DEFAULT_SWARMSYNC_MODEL).strip()
        # "auto" is a valid SwarmSync router alias — pass it through so the router
        # runs complexity scoring and selects the best model/tier. Do NOT replace it
        # with a hardcoded model string here; doing so disables smart routing entirely.
        model_candidates = [primary or model, "openrouter/free", "minimax/minimax-m2.5:free"]
        deduped: list[str] = []
        for m in model_candidates:
            if m and m not in deduped:
                deduped.append(m)

        headers = {
            "Authorization": f"Bearer {self.llm_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=120)
        last_error = "unknown"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for routed_model in deduped:
                body: dict[str, Any] = {
                    "model": routed_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "tools": tools if tools else None,
                    "tool_choice": "auto" if tools else None,
                }
                body = {k: v for k, v in body.items() if v is not None}
                async with session.post(self.llm_url, headers=headers, json=body) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    text = await resp.text()
                    last_error = f"LLM HTTP {resp.status}: {text[:500]}"
                    combined = text.lower()
                    if resp.status in (400, 402, 429) or any(
                        x in combined for x in ("402", "credit", "balance", "quota", "payment")
                    ):
                        log.warning(
                            "LLM call failed status=%s model=%s; trying next model",
                            resp.status,
                            routed_model,
                        )
                        continue
                    raise RuntimeError(last_error)
        raise RuntimeError(last_error)
