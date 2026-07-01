---
name: changelog
paths: [".no-match"]
---

# Changelog

All notable changes to the claude-rules repo.

## [0.3.0] - 2025-05-01

### Added
- 20 new rules from project AGENTS.md files and session memory:
  - **rust/** (3): `no-unwrap-in-production`, `test-through-real-subprocess-boundaries`, `cargo-check-before-commit`
  - **auth/** (1): `per-agent-auth-isolation`
  - **git/** (4): `one-concern-per-pr`, `multi-agent-git-safety`, `no-mixed-formatting-and-feature`, `conventional-commits`
  - **typescript/** (1): `explicit-return-types-everywhere`
  - **react/** (3): `fire-analytics-in-all-paths`, `inset-box-shadow-edit-mode`, `purity-in-memo-and-reducers`
  - **testing/** (2): `test-isolation-ephemeral`, `phase-transition-testing`
  - **general/** (6): `pnpm-only-package-manager`, `no-patching-packages`, `file-references-repo-relative`, `just-task-runner`, `clear-review-queue-first`, `never-hand-edit-lessons`

### Changed
- Repo-wide quality audit (222 files):
  - Added YAML frontmatter (`name` + `paths`) to all 227 files (was 53% coverage)
  - Normalized `paths:` to `triggers:` across 75 files (later corrected back to `paths:` per Claude Code spec)
  - Removed legacy `description:/globs:/alwaysApply:` fields from 37 files
  - Merged 4 duplicate rule pairs into canonical versions
  - Moved 9 root-level files into proper category directories
  - Renamed 51 files with clearer, self-documenting names
  - Fixed 58 headings that were just echoing the filename slug
  - Updated README with category table and rule format documentation
  - Added this CHANGELOG

### Removed
- `react-native/no-es2023-array-hermes.md` (merged into `brownfield/hermes-no-es2023-array.md`)
- `brownfield/brownfield-cli-not-raw-xcodebuild.md` (merged into `ci/brownfield-cli-over-xcodebuild.md`)
- `ci/plistbuddy-over-build-settings.md` (merged into `brownfield/plistbuddy-secrets-after-build.md`)
- `brownfield/dual-arch-cold-build-times.md` (merged into `ci/cold-build-timeout-buffer.md`)

## [0.2.0] - 2026-04-30

### Added
- Initial public release with 213 rules across 20 categories
- Rules sourced from tap, pawrrtal, and CI debugging sessions

## [0.1.0] - 2026-04-05

### Added
- Initial repo setup with rules from prior React Native project
