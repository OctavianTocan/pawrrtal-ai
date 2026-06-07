"""Tests for hardened CLI plugin subprocess execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.plugins.cli_runner import CliRunRequest, run_cli_plugin
from app.plugins.errors import PluginRuntimeError


def _request(
    tmp_path: Path,
    argv: tuple[str, ...],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    output_cap_bytes: int = 32_000,
) -> CliRunRequest:
    """Build a runner request with plugin and workspace dirs."""
    plugin_dir = tmp_path / "plugin"
    workspace_root = tmp_path / "workspace"
    plugin_dir.mkdir()
    workspace_root.mkdir()
    return CliRunRequest(
        argv=argv,
        plugin_dir=plugin_dir,
        workspace_root=workspace_root,
        cwd_mode="plugin",
        env=env or {},
        timeout_seconds=timeout_seconds,
        output_cap_bytes=output_cap_bytes,
    )


def test_cli_runner_scrubs_env_and_injects_declared_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOULD_NOT_LEAK", "yes")
    code = (
        "import json, os; "
        "print(json.dumps({"
        "'token': os.getenv('PLUGIN_TOKEN'), "
        "'leak': os.getenv('SHOULD_NOT_LEAK'), "
        "'home': os.getenv('HOME')"
        "}))"
    )

    result = asyncio.run(
        run_cli_plugin(
            _request(
                tmp_path,
                ("python3", "-c", code),
                env={"PLUGIN_TOKEN": "secret"},
            )
        )
    )

    payload = json.loads(result.stdout)
    assert payload["token"] == "secret"
    assert payload["leak"] is None
    assert "paw-plugin-home-" in payload["home"]


def test_cli_runner_times_out_and_marks_result(tmp_path: Path) -> None:
    result = asyncio.run(
        run_cli_plugin(
            _request(
                tmp_path,
                ("python3", "-c", "import time; time.sleep(2)"),
                timeout_seconds=1,
            )
        )
    )

    assert result.timed_out is True
    assert result.success is False


def test_cli_runner_caps_stdout(tmp_path: Path) -> None:
    result = asyncio.run(
        run_cli_plugin(
            _request(
                tmp_path,
                ("python3", "-c", "print('x' * 20)"),
                output_cap_bytes=5,
            )
        )
    )

    assert result.stdout == "xxxxx"
    assert result.stdout_truncated is True


def test_cli_runner_rejects_symlinked_local_entrypoint(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    workspace_root = tmp_path / "workspace"
    plugin_dir.mkdir()
    workspace_root.mkdir()
    target = plugin_dir / "target"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    (plugin_dir / "linked").symlink_to(target)

    with pytest.raises(PluginRuntimeError, match="symlink"):
        asyncio.run(
            run_cli_plugin(
                CliRunRequest(
                    argv=("./linked",),
                    plugin_dir=plugin_dir,
                    workspace_root=workspace_root,
                    cwd_mode="plugin",
                    env={},
                )
            )
        )
