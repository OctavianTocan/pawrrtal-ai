"""Database target safety checks for runtime and Paw preflight."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit

from app.infrastructure.config_urls import normalize_database_url

DEPLOYED_ENVS = frozenset({"prod", "production", "staging"})


@dataclass(frozen=True, slots=True)
class DatabaseSafetyReport:
    """Classified database target with deployment safety metadata."""

    env: str
    normalized_url: str
    redacted_target: str
    classification: str
    deployed: bool
    safe: bool
    reason: str
    hint: str | None


def classify_database_target(
    *,
    database_url: str,
    sqlite_db_filename: str,
    env: str,
    repo_root: Path,
    cwd: Path | None = None,
) -> DatabaseSafetyReport:
    """Classify the effective database target for runtime safety."""
    normalized_url = normalize_database_url(database_url, sqlite_db_filename)
    deployed = env.strip().lower() in DEPLOYED_ENVS
    classification = _classify_url(normalized_url, repo_root=repo_root, cwd=cwd or Path.cwd())
    redacted_target = redact_database_url(normalized_url)
    unsafe_reason = _unsafe_reason(classification=classification, deployed=deployed)
    if unsafe_reason is None:
        return DatabaseSafetyReport(
            env=env or "dev",
            normalized_url=normalized_url,
            redacted_target=redacted_target,
            classification=classification,
            deployed=deployed,
            safe=True,
            reason="database target is allowed for this environment",
            hint=None,
        )
    return DatabaseSafetyReport(
        env=env or "dev",
        normalized_url=normalized_url,
        redacted_target=redacted_target,
        classification=classification,
        deployed=deployed,
        safe=False,
        reason=unsafe_reason,
        hint="Set DATABASE_URL to a Postgres service URL before starting this environment.",
    )


def assert_database_target_safe(
    *,
    database_url: str,
    sqlite_db_filename: str,
    env: str,
    repo_root: Path,
    cwd: Path | None = None,
) -> None:
    """Raise when the configured DB target is unsafe for this runtime."""
    report = classify_database_target(
        database_url=database_url,
        sqlite_db_filename=sqlite_db_filename,
        env=env,
        repo_root=repo_root,
        cwd=cwd,
    )
    if report.safe:
        return
    raise RuntimeError(
        "Unsafe database target for "
        f"ENV={report.env}: {report.redacted_target} "
        f"({report.classification}). {report.reason} {report.hint}"
    )


def redact_database_url(url: str) -> str:
    """Return ``url`` with any password removed from the authority."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _classify_url(normalized_url: str, *, repo_root: Path, cwd: Path) -> str:
    """Return a stable label for the DB target."""
    scheme = urlparse(normalized_url).scheme
    if scheme.startswith("postgresql"):
        return "postgres"
    if scheme.startswith("sqlite"):
        return _sqlite_classification(normalized_url, repo_root=repo_root, cwd=cwd)
    return "unknown"


def _sqlite_classification(normalized_url: str, *, repo_root: Path, cwd: Path) -> str:
    """Classify SQLite as memory, repo-local, or external local file."""
    sqlite_path = _sqlite_path(normalized_url, cwd=cwd)
    if sqlite_path is None:
        return "sqlite-memory"
    if _is_relative_to(sqlite_path.resolve(), repo_root.resolve()):
        return "sqlite-repo-local"
    return "sqlite-local"


def _sqlite_path(normalized_url: str, *, cwd: Path) -> Path | None:
    """Return the SQLite filesystem path, or ``None`` for in-memory DBs."""
    marker = ":///"
    if marker not in normalized_url:
        return None
    raw_path = normalized_url.split(marker, 1)[1]
    if raw_path in {":memory:", ""}:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return cwd / path


def _unsafe_reason(*, classification: str, deployed: bool) -> str | None:
    """Return why the classification is unsafe, if it is."""
    if not deployed:
        return None
    if classification.startswith("sqlite"):
        return "SQLite is only allowed for local development."
    if classification == "unknown":
        return "Only Postgres database URLs are allowed for deployed environments."
    return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Compatibility wrapper for ``Path.is_relative_to``."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
