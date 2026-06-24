#!/usr/bin/env bash
# Populate backend/vendor/effect-api-layout/ — local architecture-reference
# clone for module layout and thin-handler patterns. Gitignored; never committed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/backend/vendor/effect-api-layout"
TARGET_REL="backend/vendor/effect-api-layout/"
GITIGNORE="${ROOT}/.gitignore"

if ! git -C "${ROOT}" check-ignore -q "${TARGET_REL}" 2>/dev/null; then
  echo "error: ${TARGET_REL} is not gitignored — add backend/vendor/effect-api-layout/ to .gitignore before populating." >&2
  exit 1
fi

mkdir -p "${ROOT}/backend/vendor"

populate_from_rsync() {
  local src="$1"
  if [[ ! -d "${src}" ]]; then
    echo "error: ARCH_REF_SRC is not a directory: ${src}" >&2
    exit 1
  fi
  echo "Syncing architecture reference from ${src} -> ${TARGET}"
  rsync -a --delete --exclude .git "${src}/" "${TARGET}/"
}

populate_from_clone() {
  local url="$1"
  if [[ -d "${TARGET}/.git" ]]; then
    echo "Updating existing clone at ${TARGET}"
    git -C "${TARGET}" fetch --depth 1 origin
    git -C "${TARGET}" checkout FETCH_HEAD
  elif [[ -d "${TARGET}" ]] && [[ -n "$(ls -A "${TARGET}" 2>/dev/null)" ]]; then
    echo "error: ${TARGET} exists but is not a git clone — remove it or set ARCH_REF_SRC for rsync." >&2
    exit 1
  else
    echo "Cloning architecture reference into ${TARGET}"
    rm -rf "${TARGET}"
    git clone --depth 1 "${url}" "${TARGET}"
  fi
}

if [[ -n "${ARCH_REF_SRC:-}" ]]; then
  populate_from_rsync "${ARCH_REF_SRC}"
elif [[ -n "${ARCH_REF_REPO_URL:-}" ]]; then
  populate_from_clone "${ARCH_REF_REPO_URL}"
else
  # Default: sibling reference monorepo if present (override with ARCH_REF_SRC).
  for candidate in "${ROOT}/../effect-api-layout-src" "${ROOT}/../reference-monorepo"; do
    if [[ -d "${candidate}" ]]; then
      populate_from_rsync "${candidate}"
      exit 0
    fi
  done
  echo "Set ARCH_REF_SRC (local directory) or ARCH_REF_REPO_URL (git URL) to populate ${TARGET}." >&2
  echo "Example: ARCH_REF_SRC=/path/to/reference-monorepo ${0}" >&2
  exit 1
fi

echo "Done. ${TARGET_REL} is gitignored ($(git -C "${ROOT}" check-ignore -v "${TARGET_REL}" | head -1))."
