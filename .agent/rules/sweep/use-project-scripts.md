---
name: use-project-scripts
paths: ["**/*"]
---
# Use Project Scripts for Git Operations

Before running raw git commands for push, deploy, or other operations,
check whether the project has wrapper scripts in `scripts/` or commands
in the Justfile. Projects with multi-account setups, custom auth, or
CI integrations often have scripts that handle edge cases raw git does not.

## Verify

"Am I about to run `git push`? Does this project have a `scripts/push.sh`
or a `just push` command? Use that instead."

## Patterns

1. Before `git push`, check for `scripts/push.sh` or `just push`
2. Before deploying, check for `just deploy` or `scripts/deploy.sh`
3. If the raw command fails with auth/permission errors, the project
   script likely handles that case -- use it
