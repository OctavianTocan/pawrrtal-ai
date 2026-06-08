# Plugin Runtime

This package is the plugin runtime host plus trusted bundled plugin
implementations.

Core runtime modules such as `manifest.py`, `discovery.py`, `registry.py`,
`state.py`, and `adapters/` load manifest data, apply enabled/disabled state,
resolve env requirements, and turn capabilities into runtime adapters.

Bundled implementation packages such as `active_recall/`, `notion/`, `tasks/`,
and tool packages are imported only after the manifest layer allows them.

The matching bundled manifests live under `backend/plugins/`. Keep that
directory declarative:

- Add or edit plugin metadata in `backend/plugins/<plugin_id>/plugin.json`.
- Add trusted Python implementation code here when a bundled manifest needs it.
- Do not add workspace or third-party plugin code here.
- Do not make providers, channels, or tools import each other directly; expose
  them through manifest capabilities and runtime adapters.
