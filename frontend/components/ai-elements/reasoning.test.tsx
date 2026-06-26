import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Reasoning, ReasoningContent, ReasoningTrigger } from './reasoning';

describe('Reasoning', () => {
  it('renders the trigger + content body', () => {
    const { getByText } = render(
      <Reasoning defaultOpen isStreaming={false}>
        <ReasoningTrigger>Show reasoning</ReasoningTrigger>
        <ReasoningContent>Some chain-of-thought text.</ReasoningContent>
      </Reasoning>
    );
    expect(getByText('Show reasoning')).toBeTruthy();
    expect(getByText('Some chain-of-thought text.')).toBeTruthy();
  });

  it('renders without crashing while still streaming', () => {
    const { getByText } = render(
      <Reasoning defaultOpen isStreaming>
        <ReasoningTrigger>Reasoning</ReasoningTrigger>
        <ReasoningContent>partial&hellip;</ReasoningContent>
      </Reasoning>
    );
    expect(getByText(/partial/)).toBeTruthy();
  });
});
