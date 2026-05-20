"""Tests for the Telegram ``/login xai`` command (#372)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.telegram.login_command import (
    LOGIN_XAI_SUBCOMMAND,
    handle_login_command,
    persist_xai_oauth_grant,
)
from app.integrations.xai import DeviceCodeGrant, DeviceCodeRequest, OAuthError
from app.integrations.xai.credentials import (
    ACCESS_TOKEN_KEY,
    EXPIRES_AT_KEY,
    REFRESH_TOKEN_KEY,
)


def _sender(*, user_id: int = 42, chat_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, chat_id=chat_id)


@pytest.mark.anyio
async def test_usage_message_when_subcommand_missing() -> None:
    """``/login`` without a sub-command surfaces a one-liner usage hint.

    Prevents an empty kickoff (no device code requested) from
    burning xAI quota on a typo.
    """
    reply = await handle_login_command(
        sender=_sender(),
        bot=AsyncMock(),
        args="",
        session=AsyncMock(),
    )
    assert "Usage" in reply
    assert LOGIN_XAI_SUBCOMMAND in reply


@pytest.mark.anyio
async def test_not_bound_when_user_has_no_telegram_binding() -> None:
    """Unbound Telegram users see the ``/start`` nudge before logging in."""
    with patch(
        "app.integrations.telegram.login_command.get_user_id_for_external",
        AsyncMock(return_value=None),
    ):
        reply = await handle_login_command(
            sender=_sender(),
            bot=AsyncMock(),
            args="xai",
            session=AsyncMock(),
        )
    assert "Connect your account" in reply


@pytest.mark.anyio
async def test_not_configured_when_oauth_client_id_unset() -> None:
    """Operator misconfiguration surfaces a clean operator hint, no OAuth call."""
    fake_user = uuid.uuid4()
    fake_settings = SimpleNamespace(xai_oauth_client_id="")
    request_spy = AsyncMock()
    with (
        patch(
            "app.integrations.telegram.login_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch("app.integrations.telegram.login_command.settings", fake_settings),
        patch(
            "app.integrations.telegram.login_command.request_device_code",
            request_spy,
        ),
    ):
        reply = await handle_login_command(
            sender=_sender(),
            bot=AsyncMock(),
            args="xai",
            session=AsyncMock(),
        )
    assert "not enabled" in reply
    assert request_spy.await_count == 0


@pytest.mark.anyio
async def test_no_workspace_message_when_user_has_no_default_workspace() -> None:
    """Users without a default workspace are bounced before kicking off the flow."""
    fake_user = uuid.uuid4()
    fake_settings = SimpleNamespace(xai_oauth_client_id="pawrrtal-client")
    with (
        patch(
            "app.integrations.telegram.login_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch("app.integrations.telegram.login_command.settings", fake_settings),
        patch(
            "app.integrations.telegram.login_command.get_default_workspace",
            AsyncMock(return_value=None),
        ),
    ):
        reply = await handle_login_command(
            sender=_sender(),
            bot=AsyncMock(),
            args="xai",
            session=AsyncMock(),
        )
    assert "default workspace" in reply


@pytest.mark.anyio
async def test_kickoff_posts_user_code_and_spawns_poll_task(tmp_path: Path) -> None:
    """The happy path returns the user code + verification URI and launches the poller."""
    fake_user = uuid.uuid4()
    fake_workspace = SimpleNamespace(path=str(tmp_path / "ws"))
    fake_settings = SimpleNamespace(xai_oauth_client_id="pawrrtal-client")
    device_request = DeviceCodeRequest(
        device_code="DEV-abc",
        user_code="ABCD-1234",
        verification_uri="https://x.ai/device",
        expires_in=600,
        interval=5,
    )
    # poll_for_token never returns here — we want the kickoff message
    # only, not the success branch. Cancel the task afterwards.
    poll_event = asyncio.Event()

    async def _hang(**_kw: object) -> DeviceCodeGrant:
        await poll_event.wait()
        return DeviceCodeGrant(access_token="x", refresh_token=None, expires_in=1, scope=None)

    with (
        patch(
            "app.integrations.telegram.login_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch("app.integrations.telegram.login_command.settings", fake_settings),
        patch(
            "app.integrations.telegram.login_command.get_default_workspace",
            AsyncMock(return_value=fake_workspace),
        ),
        patch(
            "app.integrations.telegram.login_command.request_device_code",
            AsyncMock(return_value=device_request),
        ),
        patch("app.integrations.telegram.login_command.poll_for_token", _hang),
    ):
        reply = await handle_login_command(
            sender=_sender(),
            bot=AsyncMock(),
            args="xai",
            session=AsyncMock(),
        )

    assert "ABCD-1234" in reply
    assert "https://x.ai/device" in reply
    # A background task is named ``xai-login-poll-<user-id>`` —
    # finding it tells us the kickoff actually scheduled the poll.
    tasks = [t for t in asyncio.all_tasks() if t.get_name().startswith("xai-login-poll-")]
    assert len(tasks) == 1, "expected exactly one xai-login-poll-* task"
    # Tear down so the hung task doesn't leak between tests.
    poll_event.set()
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.anyio
async def test_request_failed_message_when_device_endpoint_errs() -> None:
    """xAI device-code endpoint errors surface as a retry hint, not the user code."""
    fake_user = uuid.uuid4()
    fake_workspace = SimpleNamespace(path="/tmp/ws")
    fake_settings = SimpleNamespace(xai_oauth_client_id="pawrrtal-client")
    with (
        patch(
            "app.integrations.telegram.login_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch("app.integrations.telegram.login_command.settings", fake_settings),
        patch(
            "app.integrations.telegram.login_command.get_default_workspace",
            AsyncMock(return_value=fake_workspace),
        ),
        patch(
            "app.integrations.telegram.login_command.request_device_code",
            AsyncMock(side_effect=OAuthError("upstream borked", code="500")),
        ),
    ):
        reply = await handle_login_command(
            sender=_sender(),
            bot=AsyncMock(),
            args="xai",
            session=AsyncMock(),
        )
    assert "Couldn't reach xAI" in reply


def test_persist_xai_oauth_grant_writes_canonical_keys(tmp_path: Path) -> None:
    """The grant lands under the three canonical workspace .env keys."""
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir()
    grant = DeviceCodeGrant(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_in=3600,
        scope="chat:read",
    )

    captured: dict[str, str] = {}

    def _save(_root: Path, env: dict[str, str]) -> None:
        captured.update(env)

    with (
        patch(
            "app.integrations.telegram.login_command.load_workspace_env",
            MagicMock(return_value={}),
        ),
        patch(
            "app.integrations.telegram.login_command.save_workspace_env",
            _save,
        ),
    ):
        persist_xai_oauth_grant(workspace_root, grant)

    assert captured[ACCESS_TOKEN_KEY] == "access-1"
    assert captured[REFRESH_TOKEN_KEY] == "refresh-1"
    # ISO-8601 UTC string with a +00:00 offset, no trailing whitespace.
    assert captured[EXPIRES_AT_KEY].endswith("+00:00")
