import { describe, expect, it } from 'vitest';
import { loadDynamicFragments } from '../src/dynamic-fragments';

const REPO_ROOT = decodeURIComponent(new URL('../../../..', import.meta.url).pathname);
const FIXTURE_ROOT = `${REPO_ROOT}/packages/ci/skill-gen/e2e-test`;

describe('dynamic skill fragments', (): void => {
  it('loads CLI-owned skill fragments from the repository root', async (): Promise<void> => {
    const fragments = await loadDynamicFragments(REPO_ROOT);
    const names = fragments.map((fragment) => fragment.name);

    expect(names).toEqual(['paw', 'domain-cli']);
    expect(fragments.find((fragment) => fragment.name === 'paw')?.body).toContain('paw doctor');
  });

  it('skips dynamic sources that are absent in fixture roots', async (): Promise<void> => {
    const fragments = await loadDynamicFragments(FIXTURE_ROOT);

    expect(fragments).toEqual([]);
  });
});
