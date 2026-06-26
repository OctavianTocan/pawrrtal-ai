import { describe, expect, it } from 'vitest';
import { PROJECTS_STORAGE_KEYS } from './constants';

describe('projects constants', () => {
  it('uses the project-namespaced collapsed-projects key', () => {
    expect(PROJECTS_STORAGE_KEYS.collapsedProjects).toBe('projects:collapsed');
  });
});
