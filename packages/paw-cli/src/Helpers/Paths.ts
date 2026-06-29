import { fileURLToPath } from 'node:url';

/** Resolve the repository root from the CLI package source tree. */
export function repoRootFromSource(): string {
  return fileURLToPath(new URL('../../../..', import.meta.url));
}
