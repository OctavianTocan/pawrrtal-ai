---
name: external-scripts-over-inline-yaml
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Use External Shell Scripts Instead of Inline YAML in GitHub Actions

Category: ci
Tags: [ci, github-actions, maintainability]

## Rule

Extract non-trivial CI build logic into standalone shell or Python scripts — a 650-line YAML workflow is unmaintainable.

## Why

Shell scripts can be tested locally; YAML `run:` blocks can't. Heredocs and multiline Python inside YAML break GitHub's parser, producing "0 jobs" with no error. BSD/GNU sed differences break when moving between ubuntu and macOS runners. External scripts avoid all YAML escaping issues, are portable across runners, and are testable in isolation.

## Examples

### Bad

```yaml
# Inline heredoc breaks YAML parser — workflow reports 0 jobs
- name: Generate config
  run: |
    cat > file.txt << 'EOF'
    content here
    EOF
```

### Good

```yaml
- name: Generate config
  run: python3 scripts/ci/generate-config.py
```

## References

- rn-twinmind-brownfield-ci skill: Inline Python is a trap
- debug-ci-build-hangs skill: 5 approaches to multiline content in YAML
- Root cause of permanent workflow_dispatch 422 errors

## Verify

"Is non-trivial logic (>10 lines, heredocs, multiline Python) extracted into a standalone script? Can it be tested locally without GitHub Actions?"

## Patterns

Bad — inline heredoc in YAML:

```yaml
- name: Generate config
  run: |
    cat > file.txt << 'EOF'
    content here
    EOF
    # Heredoc content at column 1 → YAML parser sees it as keys
    # GitHub silently produces workflow with 0 jobs
```

Good — external script:

```yaml
- name: Generate config
  run: python3 scripts/ci/generate-config.py
```

Good — simple one-liners are fine inline:

```yaml
- name: Set version
  run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> "$GITHUB_ENV"
```
