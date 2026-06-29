---
name: ci-use-brew-formula-not-cask
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# CI Must Use brew install --formula, Not brew install --cask

Category: ci
Tags: [ci, macos, self-hosted, java]

## Rule

Use `brew install openjdk@17` (formula) on self-hosted CI runners, not `brew install --cask zulu@17` — cask installers require sudo.

## Why

Cask installers run `.pkg` files via `sudo`, which fails on self-hosted runners without passwordless sudo: "sudo: a terminal is required to read the password." The Homebrew formula installs without sudo. Also set `JAVA_HOME` and `GITHUB_PATH` explicitly since `/usr/libexec/java_home` may not find the brew-installed JDK.

## Examples

### Bad

```yaml
# Fails: "sudo: a terminal is required to read the password"
- name: Install Java
  run: brew install --cask zulu@17
```

### Good

```yaml
- name: Install Java (Maestro dependency)
  run: |
    if ! java -version 2>&1 | grep -q 'version'; then
      brew install openjdk@17
      echo "$(brew --prefix openjdk@17)/bin" >> "$GITHUB_PATH"
    fi
    JH=$(/usr/libexec/java_home -v 17 2>/dev/null) || \
      JH="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
    echo "JAVA_HOME=$JH" >> "$GITHUB_ENV"
```

## Verify

"Does the CI install step use `brew install <formula>` not `brew install --cask`? Is `JAVA_HOME` set explicitly after installation?"

## Patterns

Bad — cask install fails on self-hosted runners:

```yaml
# Requires interactive sudo — fails in CI
- run: brew install --cask zulu@17
  # Error: sudo: a terminal is required to read the password

# Or assumes java_home will find it
- run: brew install openjdk@17
- run: export JAVA_HOME=$(/usr/libexec/java_home -v 17)
  # May fail: java_home doesn't always find brew-installed JDKs
```

Good — formula install with explicit path configuration:

```yaml
- name: Setup Java
  run: |
    if ! java -version 2>&1 | grep -q 'version'; then
      brew install openjdk@17
    fi
    # Explicitly set paths — don't rely on java_home discovery
    JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
    echo "JAVA_HOME=$JAVA_HOME" >> "$GITHUB_ENV"
    echo "$JAVA_HOME/bin" >> "$GITHUB_PATH"
```

## References

- Maestro E2E mobile skill: Java on self-hosted CI runners
