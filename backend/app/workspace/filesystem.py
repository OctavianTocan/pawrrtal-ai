"""Filesystem helpers for workspace routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from app.schemas import WorkspaceFileNode


def safe_child(root: Path, relative: str, *, follow_final_symlink: bool = True) -> Path:
    """Resolve a workspace-relative path and verify it stays inside the root.

    Raises 400 if the path escapes the workspace root (directory traversal).
    """
    candidate = root / relative
    resolved = candidate.resolve() if follow_final_symlink else candidate.parent.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be inside the workspace",
        ) from exc
    return resolved if follow_final_symlink else candidate


def has_symlink_parent(root: Path, relative: str) -> bool:
    """Return True when any parent component in ``relative`` is a symlink."""
    current = root
    parts = Path(relative).parts[:-1]
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def build_tree(root: Path, relative_root: Path | None = None) -> list[WorkspaceFileNode]:
    """Recursively build a flat list of file-tree nodes.

    ``relative_root`` is the workspace root used to compute workspace-relative
    paths; it defaults to ``root`` on the first call.
    """
    if relative_root is None:
        relative_root = root

    nodes: list[WorkspaceFileNode] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return nodes

    for entry in entries:
        rel = entry.relative_to(relative_root).as_posix()
        if entry.is_dir():
            nodes.append(WorkspaceFileNode(name=entry.name, path=rel, is_dir=True))
            nodes.extend(build_tree(entry, relative_root))
            continue
        nodes.append(
            WorkspaceFileNode(
                name=entry.name,
                path=rel,
                is_dir=False,
                size=entry.stat().st_size,
            )
        )
    return nodes
