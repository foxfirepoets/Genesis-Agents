"""test_tool_risk_coverage.py — FINANCE-TOOL-CONTRACTS.md Section 7 Phase 1
gating test.

Imports the live tool registry and asserts every registered name has an
explicit entry in TOOL_RISK_BY_NAME. A newly registered tool with no explicit
entry must fail this test rather than silently inherit RISK_ADMIN (which
would be safe but invisible) or any other default — Phase 1's whole point is
that every name is written by hand and reviewed, never inferred.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _live_registered_names() -> set[str]:
    import tools

    tools.register_default_tools()
    return set(tools._TOOLS.keys())


class TestToolRiskByNameCoverage:
    def test_every_registered_tool_has_an_explicit_entry(self):
        from runtime.tool_policy import TOOL_RISK_BY_NAME

        live = _live_registered_names()
        missing = live - set(TOOL_RISK_BY_NAME)
        assert missing == set(), (
            f"registered tools with no TOOL_RISK_BY_NAME entry (Section 7 "
            f"Phase 1 requires every one written by hand): {sorted(missing)}"
        )

    def test_no_orphan_entries_for_names_no_longer_registered(self):
        """Not a hard failure mode Section 7 mandates, but an orphan entry is
        exactly the kind of drift the mismatch bug itself was made of — flag
        it loudly rather than let TOOL_RISK_BY_NAME silently grow stale."""
        from runtime.tool_policy import TOOL_RISK_BY_NAME

        live = _live_registered_names()
        orphans = set(TOOL_RISK_BY_NAME) - live
        assert orphans == set(), (
            f"TOOL_RISK_BY_NAME entries for tools no longer registered — "
            f"remove or confirm the tool was intentionally deleted: {sorted(orphans)}"
        )

    def test_get_tool_risk_by_name_matches_the_table(self):
        from runtime.tool_policy import TOOL_RISK_BY_NAME, get_tool_risk_by_name

        for name, expected in TOOL_RISK_BY_NAME.items():
            assert get_tool_risk_by_name(name) == expected

    def test_unknown_tool_is_admin_risk_fail_closed(self):
        from runtime.tool_policy import RISK_ADMIN, get_tool_risk_by_name

        assert get_tool_risk_by_name("totally_unknown_tool_xyz") == RISK_ADMIN

    def test_prohibited_tool_resolves_to_prohibited_not_the_table_value(self):
        """Prohibition (Section 6) must win even for a name that also happens
        to have a TOOL_RISK_BY_NAME entry, mirroring get_tool_risk's own
        prohibition-first precedence."""
        from runtime.tool_policy import (
            PROHIBITED_TOOLS,
            RISK_PROHIBITED,
            get_tool_risk_by_name,
        )

        for name in PROHIBITED_TOOLS:
            assert get_tool_risk_by_name(name) == RISK_PROHIBITED

    def test_shadow_table_does_not_change_legacy_enforcement(self):
        """Phase 1 is observability-only. check_tool_policy must be
        untouched: every existing test_tool_policy.py assertion about legacy
        behavior must still hold after this table exists."""
        from runtime.tool_policy import check_tool_policy

        # Same fixtures test_tool_policy.py already pins as legacy behavior.
        assert check_tool_policy("genesis-meta", "genesis_call")["ok"] is True
        assert check_tool_policy("genesis-finance", "workspace_shell")["ok"] is False
        assert check_tool_policy("genesis-builder", "file_write")["ok"] is True
        # A tool this Phase-1 table newly classifies READ_ONLY must still be
        # denied under the legacy path for a slug that never had it granted —
        # proving the shadow table has zero effect on real enforcement today.
        result = check_tool_policy("genesis-billing", "billing_generate_revops_report")
        assert result["ok"] is False, (
            "legacy enforcement must be unchanged by the Phase 1 shadow "
            f"table — genesis-billing must still be denied. Got: {result}"
        )
