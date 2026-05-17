---
# pawrrtal-l9dw
title: 'Settings: Integrations section + Add Integration / Add Custom MCP modals'
status: completed
type: feature
priority: high
created_at: 2026-05-04T22:01:45Z
updated_at: 2026-05-04T22:28:13Z
---

Add a fully visual Integrations section to /settings.

## Sections
- Your Integrations list — Apple Calendar, Apple Reminders, Gmail (with collapsible per-account rows), Google Calendar (collapsible), Google Drive
- Per-row meta: name, badge (Beta/Connected/Expired), description, gear icon
- Top-right "+ Add integration" button → opens AddIntegrationModal
- AddIntegrationModal: search input + filter dropdown + "+ Add custom" button + grid of integrations (Apple Calendar, Apple Reminders, Gmail, Google Calendar, Google Drive, Outlook, AdisInsight, Ahrefs, AirOps, Airwallex Developer, etc.)
- AddCustomMCPModal: Server URL input + warning + Continue button

## Wiring
- All visual; persist toggled "connected" state to localStorage under pawrrtal:integrations
- New SettingsSection 'integrations' added to nav rail

Done — Integrations rail entry, Your Integrations list, Add Integration modal, Add Custom MCP modal.
