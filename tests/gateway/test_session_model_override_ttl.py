"""model.switch_ttl_minutes: manual /model overrides expire (default 60 min), across restarts."""

from __future__ import annotations

import time

from gateway.run import GatewayRunner

_expired = GatewayRunner._session_model_override_expired
CFG_60 = {"model": {"switch_ttl_minutes": 60}}


def test_fresh_override_is_kept():
    assert _expired({"set_at": time.time() - 59 * 60}, CFG_60) is False


def test_override_older_than_ttl_expires():
    assert _expired({"set_at": time.time() - 61 * 60}, CFG_60) is True


def test_persisted_string_timestamp_is_honored():
    # sanitize_model_override persists values as strings
    assert _expired({"set_at": str(time.time() - 10)}, CFG_60) is False
    assert _expired({"set_at": str(time.time() - 2 * 3600)}, CFG_60) is True


def test_override_without_timestamp_is_expired():
    assert _expired({"model": "claude-opus-5-5"}, CFG_60) is True


def test_zero_ttl_disables_expiry():
    assert _expired({"set_at": 0}, {"model": {"switch_ttl_minutes": 0}}) is False


def test_default_ttl_is_60_minutes():
    assert _expired({"set_at": time.time() - 59 * 60}, {"model": {}}) is False
    assert _expired({"set_at": time.time() - 61 * 60}, {"model": {}}) is True


def test_expired_override_falls_back_to_config_default(monkeypatch):
    runner = object.__new__(GatewayRunner)
    runner._session_model_overrides = {
        "sess-ttl": {"model": "claude-opus-5-5", "provider": "anthropic_proxy", "api_key": "***",
                     "base_url": "http://127.0.0.1:18801", "api_mode": "anthropic_messages",
                     "set_at": time.time() - 2 * 3600},
    }
    runner._evict_cached_agent = lambda *_a, **_k: None
    runner.session_store = None
    monkeypatch.setattr("gateway.run._resolve_runtime_agent_kwargs",
                        lambda *a, **k: {"provider": "litellm_proxy", "api_key": "***",
                                         "base_url": "http://glm", "api_mode": "chat_completions"})
    model, runtime = runner._resolve_session_agent_runtime(
        session_key="sess-ttl",
        user_config={"model": {"default": "GLM-5.3-Flash", "switch_ttl_minutes": 60}},
    )
    assert model == "GLM-5.3-Flash"
    assert runtime.get("provider") != "anthropic_proxy"
    assert "sess-ttl" not in runner._session_model_overrides
