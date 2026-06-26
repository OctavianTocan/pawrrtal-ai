import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Conversation, ConversationContent, ConversationEmptyState } from './conversation';

describe('Conversation', () => {
  it('renders the StickToBottom region with the log role', () => {
    const { getByRole } = render(
      <Conversation>
        <ConversationContent>
          <p>Hello</p>
        </ConversationContent>
      </Conversation>
    );
    expect(getByRole('log')).toBeTruthy();
  });
});

describe('ConversationEmptyState', () => {
  it('renders the default empty title + description', () => {
    const { getByText } = render(<ConversationEmptyState />);
    expect(getByText('No messages yet')).toBeTruthy();
    expect(getByText('Start a conversation to see messages here')).toBeTruthy();
  });

  it('honors custom title and description', () => {
    const { getByText } = render(<ConversationEmptyState description="say hi" title="empty" />);
    expect(getByText('empty')).toBeTruthy();
    expect(getByText('say hi')).toBeTruthy();
  });

  it('renders custom children instead of the default copy', () => {
    const { getByText } = render(
      <ConversationEmptyState>
        <p>custom</p>
      </ConversationEmptyState>
    );
    expect(getByText('custom')).toBeTruthy();
  });
});
