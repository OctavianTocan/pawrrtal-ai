# Contract: CLI Config Resolution

## Sources

The CLI resolves supported settings from these sources, in order:

1. Explicit command flag.
2. Environment variable decoded through the env config descriptor.
3. Project-local `paw.toml`.
4. Active profile TOML under the CLI config root.
5. User config TOML under the CLI config root.
6. Built-in default.

Empty or whitespace-only values are unset at every layer.

## Environment Variables

| Variable | Decoded Field | Behavior |
| --- | --- | --- |
| `PAW_HOME` | `pawHome` | Overrides both config and cache roots with `config/` and `cache/` children. |
| `PAW_PROFILE` | `pawProfile` | Selects active profile when `--profile` is absent. |
| `PAW_BACKEND_URL` | `pawBackendUrl` | Selects backend target when `--backend-url` is absent. |
| `XDG_CONFIG_HOME` | `xdgConfigHome` | Base path for config root when `PAW_HOME` is absent. |
| `XDG_CACHE_HOME` | `xdgCacheHome` | Base path for cache root when `PAW_HOME` is absent. |

Environment values must be read through a deterministic Effect config descriptor against a supplied provider.

## TOML Files

Supported project/user/profile TOML keys:

| TOML Key | Decoded Field | Notes |
| --- | --- | --- |
| `profile` | `profile` | Optional profile name. |
| `backend_url` | `backendUrl` | Preferred backend target spelling. |
| `backendUrl` | `backendUrl` | Backward-compatible accepted spelling for current first-slice config. |

Rules:

- TOML parsing may still use Bun's TOML parser, but parsed `unknown` data must be decoded through the TOML config schema before use.
- Supported keys with non-string values fail with a config error naming the file source.
- Unknown non-secret keys are tolerated for future feature-owned config.
- Secret-like persisted keys fail validation before profile config is written or trusted.

## Source Labels

Resolved active context must report source labels using the existing style:

- `flag`
- `env:<VARIABLE>`
- `project:<path>`
- `profile:<path>`
- `user:<path>`
- `env:PAW_HOME`
- `env:XDG_CONFIG_HOME`
- `env:XDG_CACHE_HOME`
- `home-default`
- `default`
- `unset`

## Precedence Details

Profile resolution:

1. `--profile`
2. `PAW_PROFILE`
3. project `paw.toml`
4. user config
5. `default`

Backend target resolution:

1. `--backend-url`
2. `PAW_BACKEND_URL`
3. project `paw.toml`
4. active profile config
5. user config
6. unset

State root resolution:

1. `PAW_HOME`
2. `XDG_CONFIG_HOME` or `XDG_CACHE_HOME`
3. home defaults

## Failure Contract

Config failures must:

- Use the public `config` error kind.
- Exit with the local/config error code.
- Include the failing config source in the message or verbose details.
- Avoid printing secret values.
