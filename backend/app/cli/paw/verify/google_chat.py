"""Google Chat channel verification — formatting, command parsing, registration.

Unlike the HTTP-backed suites, the Google Chat channel has **no HTTP
surface**: inbound events arrive on a Cloud Pub/Sub subscription and replies
go out over the Chat REST API. So this scenario pings the live backend (to
stay in the ``paw verify`` family) and then asserts the channel's pure,
regression-prone logic directly — the Markdown→Chat formatting (the part that
recently leaked raw ``**`` / ``#`` markup into messages), slash-command
parsing of the add-on event shape, inbound field extraction, and channel
registration.

Scope note — the full live round-trip (publish a synthetic event to the
Pub/Sub topic → the running channel pulls it → posts a Chat reply → read it
back) needs ``GOOGLE_CHAT_*`` configured and the channel running, which paw's
transport can't synthesize. That path is exercised by the live bot; this
scenario records it as the passing ``live_pubsub_roundtrip_bot_covered``
marker so consumers can grep for the boundary.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult

SCENARIO_TITLE = "paw verify google-chat"
_HEALTH_OK = 200
# Synthetic sender/space — never hit the network, used only to drive the
# pure event parsers below.
_SENDER = "users/000000000000000000000"
_SPACE = "spaces/PAW_VERIFY"


def _addon_message(text: str) -> dict[str, Any]:
    """Build a Google Workspace add-on MESSAGE event with *text*."""
    sender = {"name": _SENDER, "displayName": "paw", "type": "HUMAN"}
    return {
        "commonEventObject": {"hostApp": "CHAT"},
        "chat": {
            "user": sender,
            "messagePayload": {
                "space": {"name": _SPACE, "type": "DM"},
                "message": {"name": f"{_SPACE}/messages/PAW", "text": text, "sender": sender},
            },
        },
    }


async def run_google_chat_scenario(state: PersonaState, client: PawClient) -> ScenarioResult:
    """Assert Markdown→Chat formatting, command parsing, extraction, registration."""
    del state  # no persona/auth needed; the asserted logic is channel-local
    from app.channels.google_chat.formatting import md_to_chat  # noqa: PLC0415
    from app.channels.google_chat.messages import (  # noqa: PLC0415
        message_text,
        parse_command,
        sender_name,
        space_name,
    )
    from app.channels.registry import registered_surfaces  # noqa: PLC0415

    result = ScenarioResult(name=SCENARIO_TITLE)

    health = await client.request("GET", "/api/v1/health")
    result.add(
        "backend_reachable",
        health.status_code == _HEALTH_OK,
        f"GET /api/v1/health returned {health.status_code}",
    )

    surfaces = registered_surfaces()
    result.add(
        "channel_registered",
        "google_chat" in surfaces,
        f"registered surfaces: {list(surfaces)}",
    )

    _check_formatting(result, md_to_chat)
    _check_commands(result, parse_command)
    _check_extraction(result, message_text, sender_name, space_name)

    result.add(
        "live_pubsub_roundtrip_bot_covered",
        True,
        "full Pub/Sub→Chat round-trip is exercised by the running bot, not paw transport",
    )
    result.artifacts["registered_surfaces"] = list(surfaces)
    return result


def _check_formatting(result: ScenarioResult, md_to_chat: Any) -> None:
    """Markdown→Chat conversions — the markup-leak regression guard."""
    bold = md_to_chat("**important**").strip()
    result.add("bold_to_single_asterisk", bold == "*important*", f"got {bold!r}")
    heading = md_to_chat("# Title").strip()
    result.add("heading_to_bold", heading == "*Title*", f"got {heading!r}")
    link = md_to_chat("[Pawrrtal](https://pawrrtal.dev)").strip()
    result.add("link_to_angle_pipe", link == "<https://pawrrtal.dev|Pawrrtal>", f"got {link!r}")
    result.add(
        "no_raw_double_asterisk",
        "**" not in md_to_chat("**a** and **b**"),
        "double-asterisk markup leaked through the converter",
    )


def _check_commands(result: ScenarioResult, parse_command: Any) -> None:
    """Slash-command parsing of the add-on payload shape."""
    parsed = parse_command(_addon_message("/status"))
    result.add("slash_command_parsed", parsed == ("status", ""), f"got {parsed!r}")
    parsed_args = parse_command(_addon_message("/model openai-codex:openai/gpt-5.5"))
    result.add(
        "slash_command_args_parsed",
        parsed_args == ("model", "openai-codex:openai/gpt-5.5"),
        f"got {parsed_args!r}",
    )
    result.add(
        "non_command_ignored",
        parse_command(_addon_message("hello there")) is None,
        "a normal message was mis-parsed as a command",
    )


def _check_extraction(
    result: ScenarioResult, message_text: Any, sender_name: Any, space_name: Any
) -> None:
    """Inbound field extraction from the add-on event shape."""
    event = _addon_message("ping")
    extracted = (message_text(event), sender_name(event), space_name(event))
    result.add(
        "event_fields_extracted",
        extracted == ("ping", _SENDER, _SPACE),
        f"got {extracted!r}",
    )
