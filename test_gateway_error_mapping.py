from fastapi import HTTPException

from main import _llm_api_key, _llm_api_url, _raise_for_runtime_failure


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
