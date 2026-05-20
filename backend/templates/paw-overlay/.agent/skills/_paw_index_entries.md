
## paw-persona
Durable Paw persona (name, vibe, working style). Defines four preset
voices (analytical, creative, direct, balanced) and keeps the JSON
identity block in `memory/personal/PREFERENCES.md` in sync.
Triggers: "set persona", "change persona", "be more direct", "be more analytical"

## paw-bootstrap
First-run conversational persona setup. Activates while the identity
block has `bootstrap_completed: false`; flips the flag once name + vibe
are recorded.
Triggers: "bootstrap", "first run", "new paw"
