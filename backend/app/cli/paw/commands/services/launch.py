"""Runtime launcher for systemd-managed Pawrrtal services."""

from __future__ import annotations

import argparse
import os
import sys

from app.cli.paw.commands.services.bws import load_secret_environment
from app.cli.paw.commands.services.targets import resolve_target


def main(argv: list[str] | None = None) -> None:
    """Load Bitwarden env and exec the production orchestrator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=None)
    args = parser.parse_args(argv)
    target = resolve_target(args.target)
    secrets = load_secret_environment(target)
    child_env = os.environ.copy()
    child_env.update(secrets)
    sys.stderr.write(f"loaded {len(secrets)} secret-backed env vars for target {target.name}\n")
    # The service launcher intentionally replaces itself with the trusted
    # repo-local runtime command so systemd receives the child exit status.
    os.execvpe("bun", ["bun", "run", "serve.ts"], child_env)  # noqa: S606


if __name__ == "__main__":
    main()
