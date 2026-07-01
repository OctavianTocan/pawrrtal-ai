# Quickstart: Effect CLI Boundaries

This guide validates the feature after implementation. It assumes dependencies are installed.

## 1. Run Focused CLI Gates

```bash
bun run --filter @pawrrtal/cli check
bun run skill-gen:check
just paw-cli-check
```

Expected outcome:

- CLI typecheck passes.
- CLI unit and integration tests pass.
- Generated `paw` and `domain-cli` skills are up to date.

## 2. Verify Structured Context Output

```bash
PAW_HOME="$(mktemp -d)" bun packages/paw-cli/src/Main.ts context --json
```

Expected outcome:

- stdout is valid JSON.
- JSON has the active context fields described in [structured-output.md](contracts/structured-output.md).
- stderr contains no progress prose.
- Exit code is `0`.

## 3. Verify Doctor Output

```bash
PAW_HOME="$(mktemp -d)" bun packages/paw-cli/src/Main.ts doctor --json
```

Expected outcome:

- stdout is valid JSON.
- JSON has `status` and `checks`.
- Every check has `name`, `status`, and `detail`.
- Exit code is `0` when no blocking check fails.

## 4. Verify Config Decode Failure

Create a temporary project config with a wrong-shaped supported value:

```bash
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/project"
printf 'profile = 123\n' > "$tmpdir/project/paw.toml"
cd "$tmpdir/project"
PAW_HOME="$tmpdir/home" bun /mnt/work/code/personal/pawrrtal/packages/paw-cli/src/Main.ts context
```

Expected outcome:

- Command exits with the local/config error code.
- stderr names the config problem and source file.
- No structured success payload is printed to stdout.

## 5. Verify Output Mode Conflict

```bash
bun packages/paw-cli/src/Main.ts context --json --plain
```

Expected outcome:

- Command exits with the usage error code.
- Error rendering uses the shared expected error shape.
- Verbose details appear only when `--verbose` is supplied.

## 6. Verify Config Precedence

Use a temporary project and state root:

```bash
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/project"
printf 'profile = "project-profile"\nbackend_url = "http://project.example"\n' > "$tmpdir/project/paw.toml"
cd "$tmpdir/project"
PAW_HOME="$tmpdir/home" PAW_PROFILE="env-profile" bun /mnt/work/code/personal/pawrrtal/packages/paw-cli/src/Main.ts context --json
```

Expected outcome:

- `profile` resolves to `env-profile`.
- `configSources` reports `env:PAW_PROFILE` for `profile`.
- Project backend target still resolves from `project:<path>` unless `PAW_BACKEND_URL` or `--backend-url` is supplied.

## 7. Run Full Repo Gate

```bash
UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check
```

Expected outcome:

- Gate exits `0`.
- Frontend warnings may print if unrelated touched files already trigger warning-level diagnostics, but CLI boundary changes must not add failures.
