## 2024-05-27 - Backend Core Layering Exceptions

**Learning:** `backend/app/core/event_bus/handlers.py` intentionally violates the `be-core -> be-crud` layer boundary (defined in `.sentrux/rules.toml` and `backend/.importlinter`) by lazy-importing `app.crud.workspace` and `app.crud.chat_message`. This was grandfathered into the CI gates because extracting the database persistence out of the event bus handler requires a proper orchestration boundary or dependency injection pattern, which wasn't built yet.

**Action:** When extracting or refactoring core orchestration logic (like agent loops or event bus handlers), avoid pushing persistence logic into the lower-level core module. Instead, invert the dependency: pass a callable (Protocol/interface) from the higher-level API/orchestration layer down into the core handler, so the core handler can trigger persistence without importing the concrete CRUD module.
