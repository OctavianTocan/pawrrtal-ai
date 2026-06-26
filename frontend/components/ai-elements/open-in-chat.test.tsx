import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OpenIn, OpenInChatGPT, OpenInClaude, OpenInContent, OpenInTrigger } from './open-in-chat';

describe('OpenIn', () => {
  it('mounts the dropdown trigger without crashing', () => {
    const { getByRole } = render(
      <OpenIn query="hello">
        <OpenInTrigger />
        <OpenInContent>
          <OpenInChatGPT />
          <OpenInClaude />
        </OpenInContent>
      </OpenIn>
    );
    expect(getByRole('button')).toBeTruthy();
  });

  it('renders the default trigger label "Open in chat" when no children supplied', () => {
    const { getByRole } = render(
      <OpenIn query="hello">
        <OpenInTrigger />
      </OpenIn>
    );
    expect(getByRole('button').textContent).toContain('Open in chat');
  });
});
