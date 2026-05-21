---
# Heartbeat checks for this workspace.
checks:
  - name: pulse
    cron: "0 9 * * *"
    prompt: |
      Daily heartbeat: summarize anything from the last 24 hours
      that needs my attention.
---

# Heartbeat

Edit the YAML front matter above to change cadences or add checks.
The body of this file is free-form context for scheduled background turns.
