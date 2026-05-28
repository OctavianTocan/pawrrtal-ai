"""Unit tests for multimodal image support in provider helpers."""

from __future__ import annotations

import pytest
from xai_sdk.proto import chat_pb2

from app.core.agent_loop.types import AgentMessage, UserMessage
from app.core.providers.gemini.messages import build_gemini_contents
from app.core.providers.litellm_provider import _build_litellm_messages
from app.core.providers.opencode_go.events import build_openai_messages
from app.core.providers.xai.messages import build_xai_messages

pytestmark = pytest.mark.anyio


class TestGeminiProviderImages:
    def test_text_only_gemini(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="hello")]
        contents = build_gemini_contents(messages)
        assert len(contents) == 1
        parts = contents[0].parts
        assert parts is not None
        assert len(parts) == 1
        assert parts[0].text == "hello"

    def test_with_image_gemini(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="describe this")]
        images = [{"data": "YWJj", "media_type": "image/jpeg"}]  # base64 for "abc"
        contents = build_gemini_contents(messages, images=images)
        assert len(contents) == 1
        parts = contents[0].parts
        assert parts is not None
        assert len(parts) == 2
        assert parts[0].text == "describe this"
        assert parts[1].inline_data is not None
        assert parts[1].inline_data.data == b"abc"
        assert parts[1].inline_data.mime_type == "image/jpeg"


class TestXaiProviderImages:
    def test_text_only_xai(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="hello")]
        messages_proto = build_xai_messages(messages, "system")
        # System prompt + user prompt
        assert len(messages_proto) == 2
        assert messages_proto[1].role == chat_pb2.MessageRole.ROLE_USER
        assert messages_proto[1].content[0].text == "hello"

    def test_with_image_xai(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="describe this")]
        images = [{"data": "YWJj", "media_type": "image/jpeg"}]
        messages_proto = build_xai_messages(messages, "system", images=images)
        assert len(messages_proto) == 2
        content = messages_proto[1].content
        assert len(content) == 2
        assert content[0].text == "describe this"
        assert content[1].image_url.image_url == "data:image/jpeg;base64,YWJj"


class TestLiteLLMProviderImages:
    def test_text_only_litellm(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="hello")]
        litellm_messages = _build_litellm_messages(messages, "system")
        assert len(litellm_messages) == 2
        assert litellm_messages[1]["role"] == "user"
        assert litellm_messages[1]["content"] == "hello"

    def test_with_image_litellm(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="describe this")]
        images = [{"data": "YWJj", "media_type": "image/jpeg"}]
        litellm_messages = _build_litellm_messages(messages, "system", images=images)
        assert len(litellm_messages) == 2
        content = litellm_messages[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "describe this"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,YWJj"


class TestOpenCodeGoProviderImages:
    def test_text_only_opencode(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="hello")]
        openai_messages = build_openai_messages(system_prompt="system", messages=messages)
        assert len(openai_messages) == 2
        assert openai_messages[1]["role"] == "user"
        assert openai_messages[1]["content"] == "hello"

    def test_with_image_opencode(self) -> None:
        messages: list[AgentMessage] = [UserMessage(role="user", content="describe this")]
        images = [{"data": "YWJj", "media_type": "image/jpeg"}]
        openai_messages = build_openai_messages(
            system_prompt="system", messages=messages, images=images
        )
        assert len(openai_messages) == 2
        content = openai_messages[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "describe this"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,YWJj"
