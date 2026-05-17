"""Adapters that connect Nexus to third-party messaging surfaces.

Each subpackage owns one provider (Telegram today; Slack / WhatsApp /
iMessage as follow-ups). Adapters are responsible for the
provider-specific I/O — translating inbound updates into Nexus's
domain calls and rendering Nexus's outbound text into the provider's
native primitives.

Plugin-style integrations (Notion, future Slack-as-tools, etc.) also
live here.  Importing this module triggers each plugin subpackage's
import, which in turn registers the plugin against
``app.core.plugins.registry`` so :func:`app.core.agent_tools.build_agent_tools`
sees it on the next chat turn.
"""

# Triggers Notion plugin registration as an import side-effect.  Kept
# at module scope so a single ``import app.integrations`` is enough to
# activate every in-tree plugin.
from app.integrations import notion  # noqa: F401
