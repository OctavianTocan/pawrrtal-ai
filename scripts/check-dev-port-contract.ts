#!/usr/bin/env bun
/**
 * Verify the dev-port contract is intact.
 *
 * Reads `frontend/package.json` and asserts its `scripts.dev` still
 * references the canonical `DEV_FRONTEND_PORT` from `scripts/dev-ports.ts`.
 * Run from CI or a pre-commit hook to catch drift between the shared
 * constant and the package-script literal (#342).
 *
 * Exit codes:
 *   0 — contract intact.
 *   1 — package.json missing or port mismatched.
 */
import { resolve } from 'node:path';

import { assertFrontendPortMatchesPackageJson } from './dev-ports';

const repoRoot = resolve(import.meta.dir, '..');
const packageJsonPath = resolve(repoRoot, 'frontend', 'package.json');

const file = Bun.file(packageJsonPath);
if (!(await file.exists())) {
  console.error(`check-dev-port-contract: ${packageJsonPath} does not exist`);
  process.exit(1);
}

try {
  assertFrontendPortMatchesPackageJson(await file.text());
  console.log('check-dev-port-contract: OK');
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`check-dev-port-contract: ${message}`);
  process.exit(1);
}
