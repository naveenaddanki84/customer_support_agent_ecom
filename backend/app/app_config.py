"""
Application configuration loaded from ``config.yaml``.

Holds non-secret, tunable settings: the agent's name and the refund-policy
thresholds the deterministic guard enforces. Secrets (API keys, DB credentials)
stay in environment variables via ``config.py`` / ``Settings``.

Any value can be overridden by an environment variable:
- AGENT_NAME
- REFUND_ESCALATION_THRESHOLD_USD
- REFUND_WINDOW_DAYS
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

logger = logging.getLogger(__name__)

# config.yaml lives at the backend root (WORKDIR /app in the container).
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass(frozen=True)
class RefundPolicyConfig:
    escalation_threshold_usd: float = 500.0
    refund_window_days: int = 30
    refundable_statuses: List[str] = field(default_factory=lambda: ["delivered", "shipped"])


@dataclass(frozen=True)
class AppConfig:
    agent_name: str = "Remi"
    refund_policy: RefundPolicyConfig = field(default_factory=RefundPolicyConfig)


def _load() -> AppConfig:
    """Load config.yaml, layer environment overrides, fall back to defaults."""
    data = {}
    try:
        if _CONFIG_PATH.is_file():
            data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - never let config break startup
        logger.error("Failed to read config.yaml (%s); using defaults: %s", _CONFIG_PATH, e)

    agent = (data.get("agent") or {})
    policy = (data.get("refund_policy") or {})

    agent_name = os.getenv("AGENT_NAME") or agent.get("name") or "Remi"

    threshold = os.getenv("REFUND_ESCALATION_THRESHOLD_USD")
    threshold = float(threshold) if threshold else float(policy.get("escalation_threshold_usd", 500))

    window = os.getenv("REFUND_WINDOW_DAYS")
    window = int(window) if window else int(policy.get("refund_window_days", 30))

    statuses = policy.get("refundable_statuses") or ["delivered", "shipped"]

    return AppConfig(
        agent_name=agent_name,
        refund_policy=RefundPolicyConfig(
            escalation_threshold_usd=threshold,
            refund_window_days=window,
            refundable_statuses=list(statuses),
        ),
    )


# Loaded once at import.
app_config = _load()
