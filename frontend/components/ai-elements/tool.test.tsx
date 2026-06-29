import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from './tool';

describe('Tool', () => {
  it('renders header title + state + content', () => {
    const { getByText, container } = render(
      <Tool defaultOpen>
        <ToolHeader state="output-available" title="search-web" type="tool-search" />
        <ToolContent>
          <ToolInput input={{ query: 'foo' }} />
          <ToolOutput errorText={undefined} output={'result'} />
        </ToolContent>
      </Tool>
    );
    expect(getByText('search-web')).toBeTruthy();
    expect(getByText('Parameters')).toBeTruthy();
    expect(container.querySelector('[data-state="open"]')).toBeTruthy();
  });

  it('renders the error path when errorText is supplied', () => {
    const { getByText } = render(
      <Tool defaultOpen>
        <ToolContent>
          <ToolOutput errorText="boom" output={undefined} />
        </ToolContent>
      </Tool>
    );
    expect(getByText(/boom/)).toBeTruthy();
  });

  describe('ToolHeader status labels (#360)', () => {
    // Past-tense labels on the terminal states so the transcript reads
    // as a log of what happened, paired with the active verb ("Running"
    // while in-flight, "Ran" once done).
    it('shows "Ran" once a tool completes successfully', () => {
      const { getByText } = render(
        <Tool defaultOpen>
          <ToolHeader state="output-available" title="search-web" type="tool-search" />
        </Tool>
      );
      expect(getByText('Ran')).toBeTruthy();
    });

    it('shows "Failed" when a tool errors', () => {
      const { getByText } = render(
        <Tool defaultOpen>
          <ToolHeader state="output-error" title="search-web" type="tool-search" />
        </Tool>
      );
      expect(getByText('Failed')).toBeTruthy();
    });

    it('still shows "Running" while a tool is in flight', () => {
      const { getByText } = render(
        <Tool defaultOpen>
          <ToolHeader state="input-available" title="search-web" type="tool-search" />
        </Tool>
      );
      expect(getByText('Running')).toBeTruthy();
    });

    it('shows "Denied" when the user blocks a tool call', () => {
      const { getByText } = render(
        <Tool defaultOpen>
          <ToolHeader state="output-denied" title="search-web" type="tool-search" />
        </Tool>
      );
      expect(getByText('Denied')).toBeTruthy();
    });
  });
});
