# Plugin Manifests

This directory is the bundled plugin manifest root. Each child directory is a
plugin package with a `plugin.json` manifest.

Manifests are declarative. They describe plugin metadata, capabilities, env
requirements, validation commands, and runtime entrypoints. They do not contain
Python implementation modules.

Runtime implementations for bundled plugins live under `backend/app/plugins/`.
That split is intentional:

- `backend/plugins/` is the control plane: discoverable plugin packages.
- `backend/app/plugins/` is the trusted runtime host and bundled implementation
  code.

External or workspace-installed plugins should follow the manifest contract
here, but they should not import arbitrary Python into the backend process. Only
trusted bundled manifests may point at `app.plugins.*` entrypoints.
