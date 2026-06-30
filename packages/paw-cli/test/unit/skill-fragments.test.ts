import { describe, expect, it } from 'vitest';
import { getSkillFragments } from '../../src/Skills/Fragments';

describe('CLI skill fragments', (): void => {
  it('generates paw and domain-cli fragments from command metadata', (): void => {
    const fragments = getSkillFragments();
    const names = fragments.map((fragment) => fragment.name);

    expect(names).toEqual(['paw', 'domain-cli']);
    expect(fragments.find((fragment) => fragment.name === 'paw')?.body).toContain('paw doctor');
    expect(fragments.find((fragment) => fragment.name === 'domain-cli')?.body).toContain('packages/paw-cli');
  });

  it('does not cite removed Python CLI paths', (): void => {
    const combined = getSkillFragments()
      .map((fragment) => fragment.body)
      .join('\n');

    expect(combined).not.toContain('backend/app/cli/paw');
    expect(combined).not.toContain('uv run paw');
    expect(combined).not.toContain('paw-extend');
  });
});
