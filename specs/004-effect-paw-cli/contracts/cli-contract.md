# CLI Contract: `paw`

This contract defines the first supported command surface for the new Effect Paw CLI package.

## Command Grammar

- Root command: `paw`.
- Resource command groups use nouns.
- Subcommands use verbs.
- Short aliases are allowed only when common and documented, such as `ls` for `list`.
- Built-in root surfaces for the first slice:
  - `paw doctor`
  - `paw context`
  - `paw completions <shell>`

## Global Options

| Option | Meaning |
| --- | --- |
| `-h`, `--help` | Print help for the current command path. |
| `-V`, `--version` | Print CLI version. |
| `-v`, `--verbose` | Print expanded diagnostics and source chains. |
| `--profile <profile>` | Run this invocation against a specific profile without changing the stored default. |
| `--backend-url <url>` | Run this invocation against a specific backend target without changing the stored default. |

Command-specific automation options:

| Option | Meaning |
| --- | --- |
| `--json` | Print structured JSON to stdout. |
| `--plain` | Print tab-separated values to stdout with no headers. |

`--json` and `--plain` are mutually exclusive.

## Output Streams

| Stream | Allowed Content |
| --- | --- |
| stdout | Command result data in human, JSON, or plain format. |
| stderr | Progress, warnings, prompts, validation errors, runtime errors, and verbose diagnostics. |

Parseable stdout must not be mixed with progress prose.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success. Health commands may use this when warnings exist but no blocking check failed. |
| `1` | Internal, local, or config error. |
| `2` | Usage, validation, or ambiguous input source. |
| `4` | Auth, permission, or active-context denial. |
| `5` | Backend, network, external process, or dependency failure. |
| `6` | Future assertion or verification failure. |

## Help Contract

Root, command-group, and command help must include:

- Summary
- Usage
- Commands or arguments
- Options
- Examples when the command does useful work
- Notes when behavior has pitfalls
- Environment variables that affect behavior

## Config Contract

Configuration resolution order:

1. Explicit command flag
2. Environment variable
3. Project-local config file
4. User config file under the CLI state root
5. Built-in default

Empty strings are treated as unset.

Recognized environment variables:

| Variable | Meaning |
| --- | --- |
| `PAW_HOME` | Override CLI state root for config and cache. |
| `PAW_PROFILE` | Active profile name when `--profile` is not supplied. |
| `PAW_BACKEND_URL` | Backend target override for commands that need a backend. |
| `XDG_CONFIG_HOME` | Optional conventional config root used only when `PAW_HOME` is unset. |
| `XDG_CACHE_HOME` | Optional conventional cache root used only when `PAW_HOME` is unset. |

`XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are not required Paw settings. They are fallback roots so the CLI behaves like a normal local tool on machines that already use XDG directories. If they are unset, the CLI falls back to home-directory defaults.

Profile resolution:

1. `--profile <profile>` for the current invocation.
2. `PAW_PROFILE`.
3. Project-local config.
4. User config under the resolved CLI state root.
5. Built-in default profile.

Examples:

```bash
paw --profile local context
PAW_PROFILE=local paw context
paw context
```

The first two examples run a command for `local` without permanently changing the stored default profile. A later feature may add a profile-management command that writes defaults; this first slice only defines resolution.

## Built-In Commands

### `paw doctor`

Checks local CLI health and reports pass, warning, and failure states.

Required checks for the first slice:

- CLI package version
- Config root resolution
- Cache root resolution
- Active profile resolution
- Backend target resolution, when configured
- Generated skills presence for `paw` and `domain-cli`

`doctor` must support human and JSON output. Plain output is allowed if it remains useful as one row per check.

### `paw context`

Prints the active CLI context without exposing secrets.

Minimum fields:

- profile
- config root
- cache root
- backend target or unset reason
- auth state when known
- config source summary

`paw whoami` is added as an alias for `paw context` and returns the same active identity/context meaning.

### `paw completions <shell>`

Generates shell completions for at least `zsh` and `bash` in the first implementation slice.

Supported shell names must be listed by help output.

## Input Source Contract

Commands that accept document, body, or bulk input must declare the allowed sources:

- inline flag value
- file path
- stdin, represented by `-` or piped input
- editor fallback

Rules:

- Exactly one body source may be selected.
- Editor fallback only runs in an interactive terminal.
- Non-interactive callers must receive exit code `2` and a message naming the accepted non-interactive alternatives.

## Removal Contract

After this feature lands:

- `scripts/paw` executes `@pawrrtal/cli`.
- `backend/pyproject.toml` no longer registers `paw = "app.cli.paw.main:app"`.
- `backend/app/cli/paw/` is not a supported runtime path.
- Generated `paw` and `domain-cli` skills do not cite deleted Python CLI source files.
- `paw-extend` is removed or no longer generated from Python CLI fragments.
