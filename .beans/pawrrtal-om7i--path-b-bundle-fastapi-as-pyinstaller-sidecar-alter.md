---
# pawrrtal-om7i
title: 'Path B: bundle FastAPI as PyInstaller sidecar (alternative)'
status: todo
type: feature
priority: low
created_at: 2026-05-05T06:08:27Z
updated_at: 2026-05-05T06:08:27Z
---

Implementation bean for **Path B** of the privileged-ops decision. Pursue **only** if Path A's two-implementation tax becomes load-bearing.

**Scope.** Bundle the FastAPI backend as a single-file binary in `electron-builder` `extraResources`. Main process spawns it on a free port at startup; existing FE points at `http://127.0.0.1:PORT` via the `BACKEND_URL` env injection that already exists in `electron/src/server.ts`.

**Steps.**
1. Add `pyinstaller` to backend `[tool.uv]` dev-deps. Spec file pinning hidden imports for `sqlalchemy.dialects.sqlite`, `tiktoken_ext.openai_public`, `fastapi_users.authentication.strategy`, etc.
2. Build target per platform: `backend-macos-arm64`, `backend-macos-x64`, `backend-linux-x64`, `backend-win-x64`. Output to `backend/dist/`.
3. `electron/package.json` `extraResources` bundles the matching binary per `electron-builder` `${arch}` token.
4. `electron/src/backend.ts` spawns the binary on a free port; passes db URL pointing at `app.getPath('userData')/pawrrtal.db`; on `before-quit` kills it cleanly.
5. CI job per platform builds the matching binary so the desktop installer is fully self-contained.

**Risks.**
- numpy/onnxruntime/cryptography native deps each have notarization quirks on macOS.
- 80–150 MB per platform. Per-arch DMG split needed.
- Subprocess lifecycle: must handle force-quit orphaning (heartbeat + parent-PID watchdog).

## Todo
- [ ] Confirm Path A wasn't sufficient
- [ ] Pin PyInstaller spec for the current backend deps
- [ ] Add per-platform CI build jobs
- [ ] Wire `electron/src/backend.ts` lifecycle + free-port allocation
- [ ] Notarization smoke test on macOS
