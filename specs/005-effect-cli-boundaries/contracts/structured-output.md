# Contract: Structured CLI Output

## General Rules

- Human output remains optimized for reading.
- Plain output remains tabular text for simple automation.
- Structured output must be encoded through the command's declared schema before writing JSON to stdout.
- Progress, warnings, prompts, and errors must not be mixed into structured stdout.
- Expected structured errors are written to stderr and encoded through the public error schema.

## `paw context --json`

Structured success shape:

```json
{
  "profile": "default",
  "configRoot": "/home/user/.config/pawrrtal",
  "cacheRoot": "/home/user/.cache/pawrrtal",
  "backendTarget": null,
  "backendTargetSource": null,
  "backendTargetUnsetReason": "No backend target configured.",
  "authState": "not_applicable",
  "configSources": [
    {
      "key": "profile",
      "source": "default",
      "value": "default"
    }
  ]
}
```

Required enums:

- `authState`: `not_applicable`, `unresolved`, `authenticated`, `unauthenticated`

## `paw doctor --json`

Structured success shape:

```json
{
  "status": "pass",
  "checks": [
    {
      "name": "cli-version",
      "status": "pass",
      "detail": "0.1.0"
    }
  ]
}
```

Required enums:

- `status`: `pass`, `warn`, `fail`
- `checks[].status`: `pass`, `warn`, `fail`

Doctor aggregate status rules:

- `fail` if any check fails.
- `warn` if no checks fail and one or more checks warn.
- `pass` otherwise.

## Structured Error JSON

Structured error shape:

```json
{
  "error": {
    "kind": "usage",
    "message": "Choose only one output mode.",
    "hint": "Use either --json or --plain, not both.",
    "details": null
  }
}
```

Required enums:

- `kind`: `usage`, `config`, `auth`, `external`, `verification`, `unexpected`

Rules:

- `hint` is `null` when absent.
- `details` is `null` unless verbose diagnostics are requested.
- Human errors may remain concise, but they must be rendered from the same expected error data.

## Formatter Contract

Each command that supports JSON output must supply:

- A command result value.
- A schema for the JSON representation.
- A pure mapping from command result to schema type when the runtime value differs from the public JSON shape.

`formatOutput` or its replacement must fail through a CLI error path if schema encoding fails. It must not silently stringify invalid output.
