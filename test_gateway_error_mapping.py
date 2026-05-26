from fastapi import HTTPException

import json

import pytest

from main import RunRequest, _llm_api_key, _llm_api_url, _raise_for_runtime_failure, run_agent


def test_runtime_failure_raises_non_200_status():
    try:
        _raise_for_runtime_failure(
            {
                "ok": False,
                "error": "llm_call_failed",
                "message": 'LLM HTTP 429: {"error":"TOO_MANY_REQUESTS"}',
            },
            "genesis-test",
        )
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.detail["agentSlug"] == "genesis-test"
        assert exc.detail["error"] == "llm_call_failed"
    else:
        raise AssertionError("expected HTTPException")


def test_timeout_maps_to_gateway_timeout():
    try:
        _raise_for_runtime_failure({"ok": False, "error": "timeout"}, "genesis-test")
    except HTTPException as exc:
        assert exc.status_code == 504
    else:
        raise AssertionError("expected HTTPException")


def test_llm_router_defaults_to_swarmsync(monkeypatch):
    monkeypatch.delenv("LLM_API_URL", raising=False)

    assert _llm_api_url() == "https://api.swarmsync.ai/v1/chat/completions"


def test_openrouter_key_is_not_default_genesis_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GENESIS_ALLOW_OPENROUTER_FALLBACK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    assert _llm_api_key() == ""


def test_openrouter_key_requires_explicit_fallback_flag(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GENESIS_ALLOW_OPENROUTER_FALLBACK", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    assert _llm_api_key() == "sk-or-test"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_slug", "expected_agent_name"),
    [
        ("genesis_builder_x402", "Genesis Builder Agent"),
        ("genesis_deploy_x402", "Genesis Deploy Agent"),
        ("genesis_qa_x402", "Genesis QA Agent"),
    ],
)
async def test_conduit_heavy_run_requests_enqueue_async_jobs(monkeypatch, request_slug, expected_agent_name):
    import main

    def fake_create_job(**kwargs):
        return {
            "id": "cqueued123",
            "status": "QUEUED",
            "created_at": "2026-05-26T00:00:00+00:00",
            "idempotent_hit": False,
        }

    def fail_get_runtime():
        raise AssertionError("async bundles must not execute AgentRuntime during /run")

    monkeypatch.setattr(main, "_JOB_STORE_OK", True)
    monkeypatch.setattr(main, "create_job", fake_create_job)
    monkeypatch.setattr(main, "_get_runtime", fail_get_runtime)

    result = await run_agent(
        request_slug,
        RunRequest(prompt="Perform a real browser-heavy task", task={"scope": "smoke"}),
    )

    payload = json.loads(result.response)
    assert result.agentName == expected_agent_name
    assert payload["slug"] == request_slug.replace("_x402", "").replace("_", "-")
    assert payload["job_id"] == "cqueued123"
    assert payload["status"] == "QUEUED"
    assert payload["poll_url"] == "/agents/jobs/cqueued123"


@pytest.mark.asyncio
@pytest.mark.parametrize("request_slug", ["onboarding_agent", "genesis_hr_x402"])
async def test_hr_aliases_use_same_canonical_bundle_in_live_test(monkeypatch, request_slug):
    import main

    async def fake_call_llm_router(system_prompt, user_prompt):
        assert "Human Resources operations specialist" in system_prompt
        return {"text": "HR response"}

    def fail_load_agent(slug):
        raise AssertionError("bundle-backed live_test calls must not load legacy Python agents")

    monkeypatch.setattr(main, "call_llm_router", fake_call_llm_router)
    monkeypatch.setattr(main, "load_agent", fail_load_agent)

    result = await run_agent(
        request_slug,
        RunRequest(prompt="Create an onboarding checklist", mode="live_test"),
    )

    payload = json.loads(result.response)
    assert result.agentName == "Genesis HR Agent"
    assert payload["slug"] == "genesis-hr"
