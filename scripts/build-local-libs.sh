#!/usr/bin/env bash
# Build local lib/* submodules so `bun install` can resolve their `link:`
# entries.  These submodules ship without a committed `dist/` directory
# (tsup output is gitignored upstream), so a fresh clone needs to build
# them once before the parent repo's install will succeed.
#
# Idempotent — skips a lib whose dist/ already looks built.
#
# Run from repo root:
#   bash scripts/build-local-libs.sh
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

# Detect the package manager available in CI.  Bun is installed before
# this step in every workflow that calls us; pnpm is the upstream lib's
# preferred manager but bun handles its package.json fine.
if command -v bun >/dev/null 2>&1; then
	PM="bun"
	INSTALL_CMD=(bun install --no-save)
	BUILD_CMD=(bun run build)
else
	echo "build-local-libs.sh: bun not found on PATH; aborting" >&2
	exit 1
fi

patch_typescript_6_tsconfig() {
	local cfg="$1/tsconfig.json"
	[ -f "$cfg" ] || return 0
	if ! grep -q '"ignoreDeprecations"' "$cfg"; then
		sed -i.bak 's|"compilerOptions": {|"compilerOptions": {\n    "ignoreDeprecations": "6.0",|' "$cfg"
		rm -f "$cfg.bak"
		echo "  patched $cfg (ignored TypeScript 6 deprecation warnings)"
	fi
}

patch_react_dropdown_tsconfig() {
	local cfg="$1/tsconfig.json"
	[ -f "$cfg" ] || return 0
	if ! grep -q '"node"' "$cfg"; then
		sed -i.bak 's|"types": \["vitest/globals"\]|"types": ["vitest/globals", "node"]|' "$cfg"
		rm -f "$cfg.bak"
		echo "  patched $cfg (added 'node' to types)"
	fi
}

# After building, dedupe shared deps that the lib brought in via its own
# package.json.  Bun's workspace hoisting leaves both copies in place when
# versions differ within the same minor; that produces multiple React /
# @types/react instances on disk and breaks tsc + vitest with confusing
# duplicate-type and "two React copies" errors.  We always want the
# parent app's version to win.
dedupe_shared_deps() {
	local lib_dir="$1"
	local nm="$lib_dir/node_modules"
	[ -d "$nm" ] || return 0
	for pkg in react react-dom @types/react @types/react-dom; do
		if [ -e "$nm/$pkg" ]; then
			rm -rf "$nm/$pkg"
			echo "  deduped $lib_dir/node_modules/$pkg (using parent's copy)"
		fi
	done
}

for lib_dir in frontend/lib/*/; do
	[ -f "$lib_dir/package.json" ] || continue
	name=$(basename "$lib_dir")
	patch_typescript_6_tsconfig "$lib_dir"
	case "$name" in
		react-dropdown) patch_react_dropdown_tsconfig "$lib_dir" ;;
	esac
	if [ -d "$lib_dir/dist" ] && [ -n "$(ls -A "$lib_dir/dist" 2>/dev/null)" ]; then
		echo "✔ $name already built (dist/ non-empty), skipping build"
		dedupe_shared_deps "$lib_dir"
		continue
	fi
	case "$name" in
		react-chat-composer)
			echo "✔ $name is vendored source — skipping pre-build"
			continue
			;;
	esac
	echo "→ building $name with $PM"
	(cd "$lib_dir" && "${INSTALL_CMD[@]}")
	(cd "$lib_dir" && "${BUILD_CMD[@]}")
	dedupe_shared_deps "$lib_dir"
	echo "✔ built $name"
done
