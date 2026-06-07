"""Regression tests for the ephemeral GitHub runner helper script."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_runner_index_discovery_uses_existing_tag_directories(tmp_path: Path) -> None:
    """cleanup --tag should discover all started runners, not the default count."""
    tag_dir = tmp_path / "runs" / "foo"
    tag_dir.mkdir(parents=True)
    for suffix in ("01", "02", "05"):
        (tag_dir / f"pawrrtal-gha-foo-{suffix}").mkdir()

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "ephemeral-self-hosted-runners.sh"
    command = f"source {script}; RUNNER_BASE={tmp_path}; RUN_TAG=foo; runner_indexes_for_tag"
    bash = shutil.which("bash")
    assert bash is not None

    # Controlled test-only shell: both the sourced script and tmp path are local.
    result = subprocess.run(  # noqa: S603
        [bash, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["1", "2", "5"]
