"""Settings, read from the environment (and ``.env`` in the project root)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    telegram_token: str = field(repr=False)  # secrets stay out of logs and tracebacks
    anthropic_api_key: str = field(repr=False)
    model: str
    effort: str | None
    fallbacks: bool
    first_screen_weight: float
    desktop_weight: float
    max_screens_desktop: int
    max_screens_mobile: int
    mobile_device: str
    browser_locale: str
    max_concurrent_checks: int
    checks_per_hour: int
    checks_per_day: int
    required_channel: str
    required_channel_url: str
    allowed_users: frozenset[int]
    allow_private_urls: bool
    capture_timeout: float
    analysis_timeout: float
    data_dir: Path
    log_level: str


def _float(name: str, default: float, lo: float, hi: float) -> float:
    value = float(os.getenv(name) or default)
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _int(name: str, default: int, lo: int) -> int:
    value = int(os.getenv(name) or default)
    if value < lo:
        raise ValueError(f"{name} must be at least {lo}, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    # The project's .env wins over inherited variables: tools export names like
    # CLAUDE_EFFORT (Claude Code sets it), which would silently change the bot's settings.
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    # low: measured ~6x cheaper and ~8x faster than medium with the same observations (see README).
    effort = (os.getenv("CLAUDE_EFFORT", "low") or "").strip().lower() or None
    if effort not in (None, "low", "medium", "high", "xhigh", "max"):
        raise ValueError(f"CLAUDE_EFFORT must be low/medium/high/xhigh/max or empty, got {effort}")
    allowed = frozenset(int(x) for x in (os.getenv("ALLOWED_USERS") or "").replace(" ", "").split(",") if x)
    data_dir = Path(os.getenv("DATA_DIR") or PROJECT_ROOT / "data")
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    return Settings(
        telegram_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip(),
        model=(os.getenv("CLAUDE_MODEL") or "claude-opus-5-5").strip(),
        effort=effort,
        fallbacks=_bool("CLAUDE_FALLBACKS", True),
        first_screen_weight=_float("FIRST_SCREEN_WEIGHT", 0.6, 0.0, 1.0),
        desktop_weight=_float("DESKTOP_WEIGHT", 0.5, 0.0, 1.0),
        max_screens_desktop=_int("MAX_SCREENS_DESKTOP", 8, 1),
        max_screens_mobile=_int("MAX_SCREENS_MOBILE", 12, 1),
        mobile_device=(os.getenv("MOBILE_DEVICE") or "iPhone 17").strip(),
        browser_locale=(os.getenv("BROWSER_LOCALE") or "en-US").strip(),
        max_concurrent_checks=_int("MAX_CONCURRENT_CHECKS", 2, 1),
        checks_per_hour=_int("CHECKS_PER_USER_PER_HOUR", 10, 0),
        checks_per_day=_int("MAX_CHECKS_PER_DAY", 0, 0),
        required_channel=(os.getenv("REQUIRED_CHANNEL") or "").strip(),
        required_channel_url=(os.getenv("REQUIRED_CHANNEL_URL") or "").strip(),
        allowed_users=allowed,
        allow_private_urls=_bool("ALLOW_PRIVATE_URLS", False),
        capture_timeout=_float("CAPTURE_TIMEOUT", 120, 10, 900),
        analysis_timeout=_float("ANALYSIS_TIMEOUT", 300, 30, 1800),
        data_dir=data_dir,
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
    )
