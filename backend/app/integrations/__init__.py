"""Adapters that connect Pawrrtal to third-party messaging surfaces.

Each subpackage owns one provider (Telegram today; Slack / WhatsApp /
iMessage as follow-ups). Adapters are responsible for the
provider-specific I/O — translating inbound updates into Pawrrtal's
domain calls and rendering Pawrrtal's outbound text into the provider's
native primitives.
"""
