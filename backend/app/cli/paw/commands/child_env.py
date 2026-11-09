"""Child-environment composition for paw orchestrators.

Lives in the commands package because it's only used by orchestrator
subcommands (``mirror``, ``fanout``) and not by any other paw surface.

The orchestrators spawn paw children as subprocesses. Inheriting the
parent's entire env was the default in v1, which sent every
``*_API_KEY``, ``GH_TOKEN``, ``AUTH_*``, and ``STRIPE_*`` to children —
including children that hit attacker-controlled upstreams in mirror's
threat model. This module switches the contract to an allowlist:
children get a minimal base env plus, when same-backend semantics make
it safe, the provider credentials they need to call the LLM.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Locale, terminal, and path variables every child needs to run as a
# normal process (find binaries, render Unicode, locate the user's home
# config dir for the python sysconfig lookup, etc).
_BASE_PASSTHROUGH_VARS: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "TERM",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_NUMERIC",
    "LC_TIME",
    "LC_COLLATE",
    "LC_MONETARY",
)

# Prefixes whose env vars are pulled through wholesale. ``PAW_*`` carries
# orchestrator-injected config (config dir, profile, backend URL).
# ``XDG_*`` is part of the standard config-discovery contract on POSIX.
_BASE_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "XDG_",
    "PAW_",
)

# Env vars that hold provider credentials. Forwarded to children only
# when the orchestrator confirms the upstream is local — see
# ``upstream_is_local`` below.
_PROVIDER_CREDENTIAL_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_CODEX_OAUTH_TOKEN",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "OPENROUTER_API_KEY",
    "PERPLEXITY_API_KEY",
)

# Env vars that hold provider credential prefixes — every var matching
# any of these is also a credential. Lets us cover, e.g., LiteLLM's
# ``LITELLM_*`` config envelope without enumerating each variant.
_PROVIDER_CREDENTIAL_PREFIXES: tuple[str, ...] = ("LITELLM_",)

# Hosts treated as "local" for the upstream-credential decision. Anything
# else is considered remote / potentially untrusted: provider credentials
# stay in the parent.
_LOCAL_HOSTNAMES: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


def upstream_is_local(url: str) -> bool:
    """Return True when ``url`` clearly targets the developer's own machine.

    Conservative: anything we can't confidently classify (parse errors,
    unusual hostnames, raw IPs outside loopback) is treated as remote.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return False
    return hostname.lower() in _LOCAL_HOSTNAMES


def build_base_child_env() -> dict[str, str]:
    """Return the minimum env every paw child needs (no provider creds).

    Pulls only the allowlisted base vars + ``PAW_*`` + ``XDG_*`` from the
    parent. Excludes ``PAW_RECORD`` so a child spawned under ``paw record``
    does not race the parent for the same fixture file.
    """
    out: dict[str, str] = {}
    for var in _BASE_PASSTHROUGH_VARS:
        value = os.environ.get(var)
        if value is not None:
            out[var] = value
    for name, value in os.environ.items():
        if name == "PAW_RECORD":
            continue
        if any(name.startswith(prefix) for prefix in _BASE_PASSTHROUGH_PREFIXES):
            out[name] = value
    return out


def add_provider_credentials(env: dict[str, str]) -> dict[str, str]:
    """Copy provider credentials from the parent into ``env`` in place.

    Returns the same dict for caller convenience. Logs at debug level so
    we can audit which secrets flow into children without spamming
    normal stdout/stderr.
    """
    forwarded: list[str] = []
    for var in _PROVIDER_CREDENTIAL_VARS:
        value = os.environ.get(var)
        if value is not None:
            env[var] = value
            forwarded.append(var)
    for name, value in os.environ.items():
        if any(name.startswith(prefix) for prefix in _PROVIDER_CREDENTIAL_PREFIXES):
            env[name] = value
            forwarded.append(name)
    if forwarded:
        logger.debug("Forwarding provider credentials to child", extra={"vars": forwarded})
    return env


def warn_on_dropped_paw_record() -> None:
    """Emit a one-line warning when the parent has ``PAW_RECORD`` set.

    Children deliberately do not inherit ``PAW_RECORD`` (each child
    needs its own fixture path or none at all), but the parent's intent
    to record is worth surfacing once per orchestrator run.
    """
    if "PAW_RECORD" in os.environ:
        logger.warning(
            "Parent has PAW_RECORD set; children will NOT inherit it. "
            "Wrap each child invocation in its own `paw record` if you "
            "need per-child fixtures."
        )
