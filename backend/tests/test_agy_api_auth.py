"""Focused tests for Antigravity auth availability checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.agy_api.auth import has_agy_api_auth


def test_has_agy_api_auth_accepts_expired_refreshable_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The picker should show AGY API models when send-time refresh can succeed."""
    token_path = tmp_path / "token.json"
    projects_path = tmp_path / "projects.json"
    workspace = tmp_path / "workspace"
    token_path.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "expired-access",
                    "refresh_token": "refresh",
                    "expiry": "2000-01-01T00:00:00Z",
                }
            }
        )
    )
    projects_path.write_text(json.dumps({str(workspace): "project-1"}))
    monkeypatch.setattr("app.providers.agy_api.auth._TOKEN_PATH", token_path)
    monkeypatch.setattr("app.providers.agy_api.auth._PROJECTS_PATH", projects_path)

    assert has_agy_api_auth(workspace) is True


def test_has_agy_api_auth_rejects_expired_token_without_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Expired AGY API tokens without refresh material are not selectable."""
    token_path = tmp_path / "token.json"
    projects_path = tmp_path / "projects.json"
    workspace = tmp_path / "workspace"
    token_path.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "expired-access",
                    "expiry": "2000-01-01T00:00:00Z",
                }
            }
        )
    )
    projects_path.write_text(json.dumps({str(workspace): "project-1"}))
    monkeypatch.setattr("app.providers.agy_api.auth._TOKEN_PATH", token_path)
    monkeypatch.setattr("app.providers.agy_api.auth._PROJECTS_PATH", projects_path)

    assert has_agy_api_auth(workspace) is False
