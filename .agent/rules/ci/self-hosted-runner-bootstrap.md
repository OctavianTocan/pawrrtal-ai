---
name: self-hosted-runner-bootstrap
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Self-Hosted Runner Bootstrap

Self-hosted Mac Mini runners need explicit tool bootstrapping. Standard GitHub Actions setup actions (setup-ruby, setup-xcode) fail with permission errors on non-GitHub-hosted runners.

## Rule

Don't use `actions/setup-ruby`, `maxim-lobanov/setup-xcode`, or similar setup actions on self-hosted runners. Instead:

1. Log pre-installed tool versions (Xcode, Node, Ruby, Homebrew)
2. Install missing tools via npm/Homebrew/gem with `--user-install` to avoid sudo
3. Add gem bin directory to `$GITHUB_PATH`
4. Cache installations to skip on subsequent runs

```yaml
- name: Bootstrap tools
  run: |
    npm install -g pnpm || true
    gem install cocoapods --user-install || true
    echo "$(ruby -e 'puts Gem.user_dir')/bin" >> $GITHUB_PATH
```

## Why

`setup-ruby` tries to create `/Users/runner/` directories that don't exist on self-hosted runners (the actual user varies per machine). `setup-xcode` requires sudo to switch Xcode versions. Using pre-installed tools cuts setup time from 5+ minutes to seconds.

## Verify

"Does this workflow avoid `setup-ruby`, `setup-xcode`, and similar actions that assume GitHub-hosted runner directory layout? Does it use `--user-install` for gems and add the bin dir to `$GITHUB_PATH`?"

## Patterns

Bad — using setup actions designed for GitHub-hosted runners:

```yaml
- uses: ruby/setup-ruby@v1
  with:
    ruby-version: '3.0'
# Error: "Permission denied - /Users/runner/.rubies"
# Self-hosted runner doesn't have /Users/runner/ directory
```

Good — bootstrap with pre-installed tools and user-level installs:

```yaml
- name: Bootstrap tools
  run: |
    echo "::group::Pre-installed versions"
    xcodebuild -version
    node --version
    ruby --version
    echo "::endgroup::"
    npm install -g pnpm || true
    gem install cocoapods --user-install || true
    echo "$(ruby -e 'puts Gem.user_dir')/bin" >> $GITHUB_PATH
```
