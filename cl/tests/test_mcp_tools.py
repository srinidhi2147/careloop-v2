import asyncio

import pytest

pytest.importorskip("mcp")

from careloop.config import Settings  # noqa: E402
from careloop.mcp_tools import build_mcp  # noqa: E402

EXPECTED_TOOLS = {
    "get_medication_schedule", "confirm_dose", "skip_dose", "get_todays_agenda",
    "notify_caregiver", "add_medication", "get_daily_summary",
}


@pytest.fixture
def mcp(seeded):
    return build_mcp(seeded, Settings())


def test_all_tools_are_registered(mcp):
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_confirm_dose_tool_changes_shared_state(mcp, seeded):
    asyncio.run(mcp.call_tool("confirm_dose", {"medication_name": ""}))
    assert seeded.state()["taken"] == 1


def test_notify_caregiver_tool_creates_alert(mcp, seeded):
    asyncio.run(mcp.call_tool("notify_caregiver", {"message": "I feel dizzy"}))
    assert "dizzy" in seeded.state()["alerts"][0]["text"]
