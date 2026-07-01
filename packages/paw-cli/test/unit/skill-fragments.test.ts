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

  it('teaches the schema and config boundary pattern', (): void => {
    const domainBody = getSkillFragments().find((fragment) => fragment.name === 'domain-cli')?.body ?? '';
    const pawBody = getSkillFragments().find((fragment) => fragment.name === 'paw')?.body ?? '';

    expect(domainBody).toContain('Schema.TaggedErrorClass');
    expect(domainBody).toContain('ConfigProvider');
    expect(domainBody).toContain('Define schemas for external input and public output');
    expect(domainBody).toContain('contract-only docstrings as first-pass requirements');
    expect(domainBody).toContain('backend/vendor/effect-smol');
    expect(domainBody).not.toContain('manual TOML record walking');
    expect(domainBody).toContain('do not add `@effect/platform-node`');
    expect(pawBody).toContain('schema-validated command data');
    expect(pawBody).toContain('structured errors are rendered on stderr');
  });
});
