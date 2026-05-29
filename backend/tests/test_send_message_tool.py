"""Tests for send_message AgentTool and make_telegram_sender.

Covers the two halves of the media delivery proof:

Part 1 — send_message AgentTool (``app.tools.send_message``)
  - text-only call succeeds (no file)
  - attachment path resolved correctly from workspace root
  - attachment outside workspace root is rejected
  - non-existent attachment is rejected
  - directory path as attachment is rejected
  - missing both text and attachment is rejected
  - MIME is auto-detected and returned in the result
  - SendFn exception surfaces as error JSON (agent can react)

Part 2 — make_telegram_sender MIME routing (``app.channels.telegram``)
  - image/*   → bot.send_photo
  - audio/ogg → bot.send_voice
  - audio/opus → bot.send_voice
  - audio/*   → bot.send_audio (non-ogg)
  - video/*   → bot.send_video
  - unknown/* → bot.send_document (fallback)
  - text-only → bot.send_message (no file)
  - message_thread_id threaded through every call when set
  - message_thread_id absent when None
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.telegram import make_telegram_sender
from app.tools.errors import ToolError, ToolErrorCode
from app.tools.send_message import _detect_mime, _resolve_attachment, make_send_message_tool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Return a temporary workspace root with a few test files."""
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "cat.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "artifacts" / "voice.ogg").write_bytes(b"OggS")
    (tmp_path / "artifacts" / "clip.mp3").write_bytes(b"ID3")
    (tmp_path / "artifacts" / "video.mp4").write_bytes(b"\x00\x00\x00\x18")
    (tmp_path / "artifacts" / "report.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "subdir").mkdir()
    return tmp_path


def _noop_send_fn() -> AsyncMock:
    """Return a no-op SendFn mock."""
    return AsyncMock(return_value=None)


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_voice = AsyncMock()
    bot.send_audio = AsyncMock()
    bot.send_video = AsyncMock()
    bot.send_document = AsyncMock()
    return bot


# ---------------------------------------------------------------------------
# Part 1 — send_message AgentTool
# ---------------------------------------------------------------------------


class TestResolveAttachment:
    def test_valid_path_resolves(self, workspace: Path) -> None:
        result = _resolve_attachment(workspace, "artifacts/cat.png")
        assert result == workspace / "artifacts" / "cat.png"

    def test_traversal_rejected(self, workspace: Path) -> None:
        with pytest.raises(ToolError) as exc_info:
            _resolve_attachment(workspace, "../../etc/passwd")
        assert exc_info.value.code == ToolErrorCode.OUT_OF_ROOT

    def test_nonexistent_rejected(self, workspace: Path) -> None:
        with pytest.raises(ToolError) as exc_info:
            _resolve_attachment(workspace, "artifacts/ghost.png")
        assert exc_info.value.code == ToolErrorCode.NOT_FOUND

    def test_directory_rejected(self, workspace: Path) -> None:
        with pytest.raises(ToolError) as exc_info:
            _resolve_attachment(workspace, "subdir")
        assert exc_info.value.code == ToolErrorCode.WRONG_KIND


class TestDetectMime:
    def test_png(self, workspace: Path) -> None:
        assert _detect_mime(workspace / "artifacts" / "cat.png") == "image/png"

    def test_ogg(self, workspace: Path) -> None:
        assert _detect_mime(workspace / "artifacts" / "voice.ogg") == "audio/ogg"

    def test_mp3(self, workspace: Path) -> None:
        assert _detect_mime(workspace / "artifacts" / "clip.mp3") == "audio/mpeg"

    def test_pdf(self, workspace: Path) -> None:
        assert _detect_mime(workspace / "artifacts" / "report.pdf") == "application/pdf"

    def test_unknown_extension_falls_back(self, tmp_path: Path) -> None:
        p = tmp_path / "file.xyzunknown"
        p.write_bytes(b"data")
        assert _detect_mime(p) == "application/octet-stream"


@pytest.mark.anyio
class TestSendMessageTool:
    async def test_text_only_calls_send_fn(self, workspace: Path) -> None:
        send_fn = _noop_send_fn()
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc1", text="Hello!")
        send_fn.assert_awaited_once_with("Hello!", None, None)
        assert '"sent": true' in result.lower() or "True" in result

    async def test_attachment_resolves_and_calls_send_fn(self, workspace: Path) -> None:
        send_fn = _noop_send_fn()
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc2", text="Here you go", attachment="artifacts/cat.png")
        args = send_fn.call_args
        assert args[0][0] == "Here you go"
        assert args[0][1] == workspace / "artifacts" / "cat.png"
        assert args[0][2] == "image/png"
        assert "cat.png" in result

    async def test_traversal_returns_error_string(self, workspace: Path) -> None:
        send_fn = _noop_send_fn()
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc3", attachment="../../etc/passwd")
        send_fn.assert_not_awaited()
        assert "error" in result.lower() or "outside" in result.lower()

    async def test_nonexistent_file_returns_error_string(self, workspace: Path) -> None:
        send_fn = _noop_send_fn()
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc4", attachment="artifacts/ghost.png")
        send_fn.assert_not_awaited()
        assert "error" in result.lower() or "not exist" in result.lower()

    async def test_missing_both_returns_error(self, workspace: Path) -> None:
        send_fn = _noop_send_fn()
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc5")
        send_fn.assert_not_awaited()
        assert (
            "least one" in result.lower()
            or "required" in result.lower()
            or "invalid" in result.lower()
        )

    async def test_send_fn_exception_returns_error_json(self, workspace: Path) -> None:
        send_fn = AsyncMock(side_effect=RuntimeError("Telegram flood control"))
        tool = make_send_message_tool(workspace_root=workspace, send_fn=send_fn)
        result = await tool.execute("tc6", text="hi", attachment="artifacts/cat.png")
        assert '"sent": false' in result.lower() or "false" in result.lower()
        assert "flood" in result.lower()

    def test_tool_name_and_schema(self, workspace: Path) -> None:
        tool = make_send_message_tool(workspace_root=workspace, send_fn=_noop_send_fn())
        assert tool.name == "send_message"
        assert "text" in tool.parameters["properties"]
        assert "attachment" in tool.parameters["properties"]


# ---------------------------------------------------------------------------
# Part 2 — make_telegram_sender MIME routing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestMakeTelegramSender:
    async def test_image_routes_to_send_photo(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("nice cat", workspace / "artifacts" / "cat.png", "image/png")
        bot.send_photo.assert_awaited_once()
        assert bot.send_video.call_count == 0
        assert bot.send_document.call_count == 0

    async def test_ogg_routes_to_send_voice(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send(None, workspace / "artifacts" / "voice.ogg", "audio/ogg")
        bot.send_voice.assert_awaited_once()
        assert bot.send_audio.call_count == 0

    async def test_opus_routes_to_send_voice(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        fake_file = workspace / "artifacts" / "voice.ogg"
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send(None, fake_file, "audio/opus")
        bot.send_voice.assert_awaited_once()

    async def test_mp3_routes_to_send_audio(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("track", workspace / "artifacts" / "clip.mp3", "audio/mpeg")
        bot.send_audio.assert_awaited_once()
        assert bot.send_voice.call_count == 0

    async def test_video_routes_to_send_video(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("clip", workspace / "artifacts" / "video.mp4", "video/mp4")
        bot.send_video.assert_awaited_once()

    async def test_pdf_routes_to_send_document(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("report", workspace / "artifacts" / "report.pdf", "application/pdf")
        bot.send_document.assert_awaited_once()

    async def test_unknown_mime_routes_to_send_document(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send(None, workspace / "artifacts" / "cat.png", "application/octet-stream")
        bot.send_document.assert_awaited_once()

    async def test_text_only_routes_to_send_message(self) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=42)
        await send("hello", None, None)
        bot.send_message.assert_awaited_once_with(chat_id=42, text="hello")
        assert bot.send_photo.call_count == 0

    async def test_thread_id_included_in_all_calls(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=5, message_thread_id=42)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("cat", workspace / "artifacts" / "cat.png", "image/png")
        call_kwargs = bot.send_photo.call_args.kwargs
        assert call_kwargs["message_thread_id"] == 42

    async def test_thread_id_absent_when_none(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=5, message_thread_id=None)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("cat", workspace / "artifacts" / "cat.png", "image/png")
        call_kwargs = bot.send_photo.call_args.kwargs
        assert "message_thread_id" not in call_kwargs

    async def test_caption_passed_with_image(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send("A dramatic cat", workspace / "artifacts" / "cat.png", "image/png")
        assert bot.send_photo.call_args.kwargs["caption"] == "A dramatic cat"

    async def test_no_caption_when_text_none(self, workspace: Path) -> None:
        bot = _make_bot()
        send = make_telegram_sender(bot, chat_id=1)
        with patch("aiogram.types.FSInputFile", MagicMock()):
            await send(None, workspace / "artifacts" / "cat.png", "image/png")
        assert bot.send_photo.call_args.kwargs["caption"] is None
