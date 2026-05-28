"""Tests for the xAI credential resolution layer (#372)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.providers.xai.credentials import (
    ACCESS_ENV_KEY,
    EXPIRES_AT_ENV_KEY,
    REFRESH_ENV_KEY,
    _needs_refresh,
    resolve_xai_credentials,
)


def test_needs_refresh_returns_false_for_empty_string() -> None:
    """No expiry recorded → no refresh needed."""
    assert _needs_refresh("") is False


def test_needs_refresh_returns_false_for_far_future() -> None:
    """Token that expires in an hour should not trigger refresh."""
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert _needs_refresh(future) is False


def test_needs_refresh_returns_true_for_near_expiry() -> None:
    """Token expiring within the lead window should trigger refresh."""
    soon = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
    assert _needs_refresh(soon) is True


def test_needs_refresh_returns_true_for_past() -> None:
    """Already-expired token should trigger refresh."""
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert _needs_refresh(past) is True


def test_needs_refresh_returns_false_for_malformed_date() -> None:
    """Garbage date string should not blow up — just skip refresh."""
    assert _needs_refresh("not-a-date") is False


@pytest.mark.anyio
async def test_resolve_returns_gateway_key_when_no_workspace() -> None:
    """No workspace → fall back to settings.xai_api_key."""
    with patch("app.core.providers.xai.credentials.settings") as mock_settings:
        mock_settings.xai_api_key = "gateway-key"
        result = await resolve_xai_credentials(None)
    assert result == "gateway-key"


@pytest.mark.anyio
async def test_resolve_returns_none_when_nothing_configured() -> None:
    """No workspace, no gateway key → None."""
    with patch("app.core.providers.xai.credentials.settings") as mock_settings:
        mock_settings.xai_api_key = ""
        result = await resolve_xai_credentials(None)
    assert result is None


@pytest.mark.anyio
async def test_resolve_prefers_oauth_over_legacy(tmp_path: Path) -> None:
    """OAuth access token beats the legacy XAI_API_KEY."""
    future_expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    env = {
        ACCESS_ENV_KEY: "oauth-token",
        REFRESH_ENV_KEY: "refresh-tok",
        EXPIRES_AT_ENV_KEY: future_expiry,
    }
    with (
        patch("app.core.providers.xai.credentials.load_workspace_env", return_value=env),
        patch("app.core.providers.xai.credentials.resolve_api_key", return_value="legacy-key"),
        patch("app.core.providers.xai.credentials.settings") as mock_settings,
    ):
        mock_settings.xai_api_key = "gateway-key"
        result = await resolve_xai_credentials(tmp_path)
    assert result == "oauth-token"


@pytest.mark.anyio
async def test_resolve_falls_back_to_legacy_when_no_oauth(tmp_path: Path) -> None:
    """No OAuth tokens → use the workspace XAI_API_KEY."""
    with (
        patch("app.core.providers.xai.credentials.load_workspace_env", return_value={}),
        patch("app.core.providers.xai.credentials.resolve_api_key", return_value="legacy-key"),
        patch("app.core.providers.xai.credentials.settings") as mock_settings,
    ):
        mock_settings.xai_api_key = "gateway-key"
        result = await resolve_xai_credentials(tmp_path)
    assert result == "legacy-key"
