---
name: no-heredoc-in-yaml-run
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# No Heredocs in YAML Run Blocks

Never use shell heredocs (`cat <<DELIM`) inside GitHub Actions `run:` blocks. The heredoc content starts at column 1, which the YAML parser interprets as new YAML keys.

## Rule

Use `echo` statements or write content from a file instead:

## Bad

```yaml
- run: |
    cat >> file.gradle.kts <<'EOF'
// This comment at column 1 breaks YAML
configurations.matching { ... }
EOF
```

The `//` and `configurations` at column 1 look like YAML keys. GitHub silently produces a workflow with 0 jobs.

## Good

```yaml
- run: |
    {
      echo "// Pin to release variant."
      echo "configurations.matching { ... }.configureEach {"
      echo "    attributes { ... }"
      echo "}"
    } >> file.gradle.kts
```

Or write the content to a temp file first and `cat` it in.

## Why

A heredoc injecting Kotlin/Gradle config into a generated build.gradle.kts broke the entire publish workflow. GitHub ran the workflow but produced zero jobs. The error was invisible: no YAML parse error in the UI, no annotation, just an empty run with conclusion "failure". Took 4 push attempts to diagnose.

## Verify

"Does my `run:` block contain any heredoc syntax (`<<DELIM`)? Could any line of the output be misinterpreted as a YAML key?"

## Patterns

Bad — heredoc inside YAML run block:

```yaml
- name: Generate config
  run: |
    cat >> build.gradle.kts <<'GRADLE'
    android {
      compileSdk = 35
    }
    GRADLE
    # YAML parser sees "android" and "compileSdk" as YAML keys
    # Workflow silently produces 0 jobs
```

Good — echo group to append content:

```yaml
- name: Generate config
  run: |
    {
      echo "android {"
      echo "  compileSdk = 35"
      echo "}"
    } >> build.gradle.kts
```
