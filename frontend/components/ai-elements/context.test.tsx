import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  Context,
  ContextCacheUsage,
  ContextContent,
  ContextContentBody,
  ContextContentFooter,
  ContextContentHeader,
  ContextInputUsage,
  ContextOutputUsage,
  ContextReasoningUsage,
  ContextTrigger,
} from './context';

const USAGE = {
  inputTokens: 100,
  outputTokens: 50,
  totalTokens: 150,
  inputTokenDetails: {
    noCacheTokens: 100,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  },
  outputTokenDetails: {
    textTokens: 50,
    reasoningTokens: 0,
  },
};

describe('Context', () => {
  it('renders the trigger with default usage display', () => {
    const { container } = render(
      <Context maxTokens={1000} modelId="test" usage={USAGE} usedTokens={150}>
        <ContextTrigger />
      </Context>
    );
    expect(container.querySelector('button')).toBeTruthy();
  });

  it('does not crash when ContextContent / usage rows are mounted (hovercard closed)', () => {
    const { container } = render(
      <Context maxTokens={1000} modelId="test" usage={USAGE} usedTokens={150}>
        <ContextTrigger />
        <ContextContent>
          <ContextContentHeader />
          <ContextContentBody>
            <ContextInputUsage />
            <ContextOutputUsage />
            <ContextReasoningUsage />
            <ContextCacheUsage />
          </ContextContentBody>
          <ContextContentFooter />
        </ContextContent>
      </Context>
    );
    expect(container.querySelector('button')).toBeTruthy();
  });
});
