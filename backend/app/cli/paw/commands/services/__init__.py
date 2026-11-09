"""Public surface for ``paw services``."""

from __future__ import annotations

# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# ---
#
# ## Service targets
#
# ```bash
# just paw services targets list
# just paw services secrets check prod --json
# just paw services install prod --dry-run
# just paw services install prod --yes
# just paw services status prod
# just paw services logs prod --follow
# just paw services uninstall prod --yes
# ```
#
# `paw services install TARGET --dry-run` previews the systemd unit. `--yes`
# writes, reloads systemd, and enables/starts it. Targets come from
# `/etc/pawrrtal/services.toml` by default, and Bitwarden secrets stay in
# `/etc/pawrrtal/bws.env`; `secrets check` validates access without printing
# secret values.
# </skill-gen>

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so services can run standalone."""
    if name == "app":
        from app.cli.paw.commands.services.cli import app  # noqa: PLC0415

        return app
    raise AttributeError(name)
