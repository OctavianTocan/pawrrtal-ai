import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GitHubIcon } from './GitHubIcon';
import { GoogleDriveIcon } from './GoogleDriveIcon';
import { LinearIcon } from './LinearIcon';
import { NotionIcon } from './NotionIcon';
import { SlackIcon } from './SlackIcon';

describe('brand icons', () => {
  const cases = [
    { name: 'Notion', Component: NotionIcon },
    { name: 'Slack', Component: SlackIcon },
    { name: 'Google Drive', Component: GoogleDriveIcon },
    { name: 'GitHub', Component: GitHubIcon },
    { name: 'Linear', Component: LinearIcon },
  ] as const;

  for (const { name, Component } of cases) {
    it(`renders the ${name} glyph with an accessible <title>`, () => {
      const { container, getByTitle } = render(<Component className="size-4" />);
      expect(container.querySelector('svg')).toBeTruthy();
      expect(getByTitle(name)).toBeTruthy();
    });

    it(`forwards className onto the ${name} <svg> root`, () => {
      const { container } = render(<Component className="size-3.5 text-foreground" />);
      expect(container.querySelector('svg')?.getAttribute('class')).toContain('size-3.5');
    });
  }
});
