"""One-shot import-rewrite for Phase 4. Delete after the commit lands."""

from __future__ import annotations

import re
from pathlib import Path

REPLACEMENTS = {
    r"from app\.db import": "from app.infrastructure.database.legacy import",
    r"from app\.db_base import": "from app.infrastructure.models.base import",
    r"from app\.users import": "from app.infrastructure.auth.users import",
    r"from app\.logger_setup import": "from app.infrastructure.logging.setup import",
    r"from app\.core\.middleware import": "from app.infrastructure.middleware.backend_api_key import",
    r"from app\.core\.rate_limit import": "from app.infrastructure.middleware.rate_limit import",
    r"from app\.core\.request_logging import": "from app.infrastructure.middleware.logging import",
}

ROOT = Path("/Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai")
SKIP = (".venv", "vendor/", "__pycache__", "node_modules")

count = 0
for path in ROOT.rglob("*.py"):
    s = str(path)
    if any(skip in s for skip in SKIP):
        continue
    try:
        c = path.read_text()
    except Exception:
        continue
    orig = c
    for pat, sub in REPLACEMENTS.items():
        c = re.sub(pat, sub, c)
    if c != orig:
        path.write_text(c)
        count += 1
print(f"updated {count} files")
