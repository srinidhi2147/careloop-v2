"""Runtime settings, read once from environment variables."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    db_path: str = "careloop.db"
    timezone: str = "Asia/Kolkata"
    grace_minutes: int = 60
    auto_missed: bool = False
    seed_demo: bool = True
    use_mock_ai: bool = False
    nebius_api_key: str = field(default="", repr=False)  # repr=False keeps the key out of logs
    nebius_base_url: str = "https://api.tokenfactory.us-north1.nebius.com/v1/"
    nebius_model_id: str = "nvidia/Nemotron-3.5-Super-VL"
    max_upload_bytes: int = 5_000_000
    mcp_allowed_hosts: tuple[str, ...] = ()  # empty = host check off (demo/tunnels); set in production
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env

        def flag(key: str, default: bool) -> bool:
            return e.get(key, "1" if default else "0") == "1"

        hosts = tuple(h.strip() for h in e.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip())
        return cls(
            db_path=e.get("CARELOOP_DB", cls.db_path),
            timezone=e.get("CARELOOP_TZ", cls.timezone),
            grace_minutes=int(e.get("GRACE_MINUTES", cls.grace_minutes)),
            auto_missed=flag("AUTO_MISSED", cls.auto_missed),
            seed_demo=flag("SEED_DEMO", cls.seed_demo),
            use_mock_ai=flag("USE_MOCK_AI", cls.use_mock_ai),
            nebius_api_key=e.get("NEBIUS_API_KEY", ""),
            nebius_base_url=e.get("NEBIUS_BASE_URL", cls.nebius_base_url),
            nebius_model_id=e.get("NEBIUS_MODEL_ID", cls.nebius_model_id),
            max_upload_bytes=int(e.get("MAX_UPLOAD_BYTES", cls.max_upload_bytes)),
            mcp_allowed_hosts=hosts,
            log_level=e.get("LOG_LEVEL", cls.log_level).upper(),
        )