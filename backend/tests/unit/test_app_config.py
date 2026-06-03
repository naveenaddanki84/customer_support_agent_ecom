"""Unit tests for config.yaml loading + env overrides."""

import app.app_config as ac


def test_loads_defaults_from_yaml():
    cfg = ac.app_config
    assert cfg.agent_name  # non-empty
    assert cfg.refund_policy.escalation_threshold_usd > 0
    assert cfg.refund_policy.refund_window_days > 0
    assert "delivered" in [s.lower() for s in cfg.refund_policy.refundable_statuses]


def test_env_overrides_agent_name(monkeypatch):
    monkeypatch.setenv("AGENT_NAME", "Zephyr")
    cfg = ac._load()
    assert cfg.agent_name == "Zephyr"


def test_env_overrides_threshold_and_window(monkeypatch):
    monkeypatch.setenv("REFUND_ESCALATION_THRESHOLD_USD", "1000")
    monkeypatch.setenv("REFUND_WINDOW_DAYS", "14")
    cfg = ac._load()
    assert cfg.refund_policy.escalation_threshold_usd == 1000.0
    assert cfg.refund_policy.refund_window_days == 14
