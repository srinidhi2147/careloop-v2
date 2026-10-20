"""MCP server (the part Alexa+ calls). Thin wrappers over CareService, no business logic here."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings
from .services import CareService


def build_mcp(service: CareService, settings: Settings) -> FastMCP:
    if settings.mcp_allowed_hosts:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.mcp_allowed_hosts),
        )
    else:  # demo and tunnel use; set MCP_ALLOWED_HOSTS in production
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    mcp = FastMCP("CareLoop", stateless_http=True, json_response=True, transport_security=security)

    @mcp.tool()
    def get_medication_schedule(pending_only: bool = True) -> dict[str, Any]:
        """Read the elder's medicines for today. Use when they ask what to take. Returns text to speak."""
        return service.get_medication_schedule(pending_only).to_dict()

    @mcp.tool()
    def confirm_dose(medication_name: str = "") -> dict[str, Any]:
        """Log a dose as taken. Use when the elder says they took their medicine."""
        return service.confirm_dose(medication_name).to_dict()

    @mcp.tool()
    def skip_dose(medication_name: str = "") -> dict[str, Any]:
        """Log a dose as skipped and tell the caregiver."""
        return service.skip_dose(medication_name).to_dict()

    @mcp.tool()
    def get_todays_agenda() -> dict[str, Any]:
        """Read today's appointments and reminders."""
        return service.get_agenda().to_dict()

    @mcp.tool()
    def notify_caregiver(message: str, urgent: bool = True) -> dict[str, Any]:
        """Send an alert to the caregiver dashboard, for example when the elder asks for help."""
        return service.notify_caregiver(message, urgent).to_dict()

    @mcp.tool()
    def add_medication(name: str, time: str, strength: str = "", instructions: str = "") -> dict[str, Any]:
        """Add a medicine to the care plan. time is HH:MM in 24-hour format."""
        return service.add_medication(name, time, strength, instructions).to_dict()

    @mcp.tool()
    def get_daily_summary() -> dict[str, Any]:
        """Plain-language summary of today's medicines for the caregiver."""
        s = service.summary()
        return {"summary": s.text, "source": s.source}

    return mcp
