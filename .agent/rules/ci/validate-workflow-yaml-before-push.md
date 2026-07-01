---
name: validate-workflow-yaml-before-push
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Validate GitHub Actions YAML with actionlint Before Pushing

Category: ci
Tags: [ci, github-actions, yaml]

## Rule

Validate workflow YAML locally before pushing — broken YAML permanently poisons `workflow_dispatch` triggers.

## Why

If GitHub's first parse of a workflow file fails (e.g., heredoc at column 1 inside `run: |`), the workflow ID gets permanently cached as "no workflow_dispatch trigger." The `workflow_dispatch` button disappears and CLI returns HTTP 422 forever. Renaming the file creates a new ID but the old broken one persists. Always validate with `python3 -c "import yaml; yaml.safe_load(open('file.yml'))"` before pushing.

## Examples

### Bad

```yaml
# Heredoc at column 1 breaks YAML parser — permanently
- name: Generate config
  run: |
    cat > file.txt << 'EOF'
    content here
    EOF
```

### Good

```bash
# Validate before push
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/e2e.yml'))"
# Use printf instead of heredocs
- name: Generate config
  run: printf 'content here\n' > file.txt
```

## References

- rn-twinmind-brownfield-ci skill: YAML heredocs break workflow_dispatch permanently
- brownfield-native-test-hosts skill: Heredoc YAML pitfall

## Verify

"Was the workflow YAML validated locally before pushing? Could a parse error permanently disable `workflow_dispatch`?"

## Patterns

Bad — push without validating YAML:

```bash
# Edit workflow with heredoc, push immediately
git add .github/workflows/publish.yml
git commit -m "fix: update workflow"
git push
# GitHub's parser chokes on heredoc → workflow_dispatch permanently disabled
# HTTP 422 on all future dispatch attempts for this workflow ID
```

Good — validate before every workflow push:

```bash
# Validate YAML syntax before pushing
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))"
# Or use actionlint
actionlint .github/workflows/publish.yml
git add .github/workflows/publish.yml
git commit -m "fix: update workflow"
git push
```
