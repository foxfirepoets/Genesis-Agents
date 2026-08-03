"""Slug-form handling: bundles use hyphens, the LIVE gateway uses underscores
with an ``_x402`` suffix. Sending the bundle form 404s.
"""

from __future__ import annotations

import asyncio

import pytest

from eval.genesis_client import (
    LIVE_SLUGS,
    GenesisClient,
    MoneyDomainBlocked,
    is_money_domain,
    resolve_live_slug,
)
from eval.tests.fakes import FakeTransport, ok_response


@pytest.mark.parametrize(
    "requested,expected",
    [
        # bundle (hyphen) form -> live form
        ("genesis-research", "genesis_research_x402"),
        ("genesis-builder", "genesis_builder_x402"),
        ("genesis-qa", "genesis_qa_x402"),
        ("genesis-seo", "genesis_seo_x402"),
        ("genesis-content", "genesis_content_x402"),
        ("genesis-security", "genesis_security_x402"),
        # already live -> unchanged
        ("genesis_research_x402", "genesis_research_x402"),
        ("genesis_meta_agent", "genesis_meta_agent"),
        ("legal_agent", "legal_agent"),
        # underscore-without-suffix -> suffixed live form
        ("genesis_research", "genesis_research_x402"),
        # aliases that do NOT follow the pattern
        ("genesis-meta", "genesis_meta_x402"),
        ("genesis-legal", "legal_agent"),
        ("genesis-hr", "onboarding_agent"),
        ("genesis-domain", "domain_name_agent"),
        ("genesis-maintenance", "maintenance_agent"),
        ("genesis-ai-vision", "genesis-ai-vision-api"),
        ("genesis-data-pipeline", "genesis-data-pipeline-agent"),
        # live slugs that keep hyphens
        ("genesis-workflow-automator", "genesis-workflow-automator"),
    ],
)
def test_resolves_to_the_live_form(requested, expected):
    resolved, _ = resolve_live_slug(requested)
    assert resolved == expected
    assert resolved in LIVE_SLUGS, f"{resolved} is not a live slug"


def test_whitespace_is_stripped():
    assert resolve_live_slug("  genesis-research  ")[0] == "genesis_research_x402"


def test_unknown_slug_is_best_effort_and_marked_unverified():
    resolved, resolution = resolve_live_slug("totally-made-up-agent")
    assert resolved == "totally_made_up_agent"
    assert resolution == "unverified"


def test_known_slug_is_marked_verified_or_aliased():
    assert resolve_live_slug("genesis-research")[1] == "verified"
    assert resolve_live_slug("genesis-legal")[1] == "aliased"


def test_empty_slug_is_rejected():
    with pytest.raises(ValueError):
        resolve_live_slug("")


def test_the_request_url_uses_the_live_form():
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, api_key="k", jitter=False)
    result = asyncio.run(client.run_agent("genesis-research", "task"))
    assert transport.calls[0]["url"].endswith("/agents/genesis_research_x402/run")
    assert result.slug == "genesis_research_x402"
    assert result.requested_slug == "genesis-research"


# ---------------------------------------------------------------------------
# Money-domain containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "genesis-finance", "genesis_finance_x402", "finance_agent",
        "genesis-billing", "genesis_billing_x402", "billing_agent",
        "genesis-commerce", "genesis_commerce_x402", "commerce_agent",
        "genesis-pricing", "pricing_agent",
    ],
)
def test_money_domain_agents_are_refused_before_any_request(slug):
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, api_key="k", jitter=False)
    with pytest.raises(MoneyDomainBlocked):
        asyncio.run(client.run_agent(slug, "task"))
    assert transport.run_call_count == 0, "a money-domain request reached the transport"
    assert transport.health_calls == 0


def test_non_money_agents_are_not_blocked():
    for slug in ("genesis-research", "genesis-qa", "genesis-content", "genesis-seo"):
        assert is_money_domain(resolve_live_slug(slug)[0]) is False


def test_the_block_is_overridable_explicitly():
    transport = FakeTransport([ok_response()])
    client = GenesisClient(
        transport=transport, api_key="k", jitter=False, allow_money_domain=True
    )
    result = asyncio.run(client.run_agent("genesis-finance", "task"))
    assert result.slug == "genesis_finance_x402"


# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------


def test_live_test_mode_sets_both_bypass_fields():
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, api_key="k", jitter=False)
    asyncio.run(client.run_agent("genesis-research", "task", mode="live_test"))
    body = transport.calls[0]["json"]
    assert body["mode"] == "live_test"
    assert body["testContext"] is True
    assert body["prompt"] == "task"


def test_full_mode_sends_no_bypass_fields():
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, api_key="k", jitter=False)
    asyncio.run(client.run_agent("genesis-research", "task", mode="full"))
    body = transport.calls[0]["json"]
    assert "mode" not in body
    assert "testContext" not in body


def test_structured_task_goes_to_input_not_prompt():
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, api_key="k", jitter=False)
    asyncio.run(client.run_agent("genesis-research", {"topic": "agents"}))
    body = transport.calls[0]["json"]
    assert body["input"] == {"topic": "agents"}
    assert "prompt" not in body


def test_invalid_mode_is_rejected():
    client = GenesisClient(transport=FakeTransport([ok_response()]), api_key="k")
    with pytest.raises(ValueError):
        asyncio.run(client.run_agent("genesis-research", "task", mode="turbo"))


def test_auth_headers_match_the_gateway_contract():
    """main.py::verify_gateway_key accepts X-Agent-Api-Key (GATEWAY_API_KEY) or
    X-Agent-Gateway-Secret (AGENT_GATEWAY_SECRET)."""
    transport = FakeTransport([ok_response()])
    client = GenesisClient(
        transport=transport, api_key="a", gateway_secret="b", jitter=False
    )
    asyncio.run(client.run_agent("genesis-research", "task"))
    headers = transport.calls[0]["headers"]
    assert headers["X-Agent-Api-Key"] == "a"
    assert headers["X-Agent-Gateway-Secret"] == "b"


def test_no_credential_configured_sends_no_auth_headers(monkeypatch):
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_GATEWAY_SECRET", raising=False)
    transport = FakeTransport([ok_response()])
    client = GenesisClient(transport=transport, jitter=False)
    assert client.has_credential() is False
    asyncio.run(client.run_agent("genesis-research", "task"))
    headers = transport.calls[0]["headers"]
    assert "X-Agent-Api-Key" not in headers
    assert "X-Agent-Gateway-Secret" not in headers
