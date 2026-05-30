"""Tests for ``app.governance.secret_redaction``.

The regex set is the surface the rest of the audit / persistence
stack relies on for "secrets never reach disk". A new secret prefix
or a regression in one pattern surfaces here first.
"""

from __future__ import annotations

import pytest

from app.governance.secret_redaction import (
    redact_mapping,
    redact_secrets,
)


class TestRedactSecretsStrings:
    """Patterns lifted from the CCT regex set must all keep matching."""

    @pytest.mark.parametrize(
        ("raw", "expected_prefix"),
        [
            (
                "key=sk-ant-api01-AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQrStUvWxYz",
                "sk-ant-api01-AbCdEfGhIj***",
            ),
            (
                "OPENAI=sk-abcdefghijklmnopqrstuvwxyz0123456789",
                "sk-abcdefghijklmnopqrst***",
            ),
            (
                "ghp_abcde0123456789abcdef",
                "ghp_abcde***",
            ),
            (
                "gho_abcde0123456789abcdef",
                "gho_abcde***",
            ),
            (
                "github_pat_abcdef0123456789",
                "github_pat_abcde***",
            ),
            (
                "xoxb-abcde-0123456789",
                "xoxb-abcde***",
            ),
            (
                "AKIAIOSFODNN7EXAMPLE",
                "AKIAIOSF***",
            ),
            (
                "claude --token=verysecret1234567890",
                "claude --token=***",
            ),
            (
                "claude --api-key=verysecret1234567890",
                "claude --api-key=***",
            ),
            (
                'TOKEN="abcdef1234567890"',
                "TOKEN=***",
            ),
            (
                "API_KEY=abcdef1234567890",
                "API_KEY=***",
            ),
            (
                "Authorization: Bearer abcdef1234567890",
                "Bearer ***",
            ),
            (
                "postgres://admin:supersecret@db.example.com/app",
                "postgres://admin:***@db.example.com/app",
            ),
        ],
    )
    def test_known_patterns_redact(self, raw: str, expected_prefix: str) -> None:
        out = redact_secrets(raw)
        assert expected_prefix in out, f"expected prefix {expected_prefix!r} in {out!r}"

    def test_idempotent(self) -> None:
        """Running redact twice on the same string is a no-op past the first pass."""
        sample = "TOKEN=abcdef1234567890"
        once = redact_secrets(sample)
        twice = redact_secrets(once)
        assert once == twice

    def test_innocuous_strings_unchanged(self) -> None:
        """Strings that don't carry any known prefix are returned verbatim."""
        sample = "This is a normal sentence about an API."
        assert redact_secrets(sample) == sample

    def test_empty_input(self) -> None:
        assert redact_secrets("") == ""

    def test_non_string_passthrough(self) -> None:
        """Non-strings are returned unchanged (the chat aggregator hands heterogeneous values)."""
        assert redact_secrets(None) is None  # type: ignore[arg-type]
        # The redact_secrets function returns non-strings unchanged.
        assert redact_secrets(42) == 42  # type: ignore[arg-type,comparison-overlap]


class TestRedactMapping:
    """The recursive walker preserves shape while scrubbing strings."""

    def test_redacts_string_values(self) -> None:
        payload = {"token": "sk-abcdefghijklmnopqrstuvwxyz0123456789", "ok": "fine"}
        out = redact_mapping(payload)
        assert isinstance(out, dict)
        assert "***" in out["token"]
        assert out["ok"] == "fine"

    def test_walks_nested_dicts(self) -> None:
        payload = {
            "outer": {
                "inner": "TOKEN=abcdef1234567890",
                "fine": "hello",
            }
        }
        out = redact_mapping(payload)
        assert "***" in out["outer"]["inner"]
        assert out["outer"]["fine"] == "hello"

    def test_walks_lists(self) -> None:
        payload = {"args": ["--token=verysecret123", "--verbose"]}
        out = redact_mapping(payload)
        assert "***" in out["args"][0]
        assert out["args"][1] == "--verbose"

    def test_preserves_scalar_types(self) -> None:
        payload = {"n": 42, "flag": True, "none": None, "f": 1.5}
        out = redact_mapping(payload)
        assert out == payload

    def test_returns_passthrough_for_non_collection(self) -> None:
        assert redact_mapping(42) == 42
        assert redact_mapping(None) is None
        assert redact_mapping(True) is True
