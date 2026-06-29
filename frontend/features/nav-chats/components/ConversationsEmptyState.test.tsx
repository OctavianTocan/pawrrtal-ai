import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConversationsEmptyState } from './ConversationsEmptyState';

describe('ConversationsEmptyState', () => {
  it('renders the title, description, and supplied icon', () => {
    const { getByText } = render(
      <ConversationsEmptyState
        description="Start a chat to see it land in the sidebar."
        icon={<span data-testid="icon">⚙️</span>}
        title="Nothing here yet"
      />
    );
    expect(getByText('Nothing here yet')).toBeTruthy();
    expect(getByText(/Start a chat/)).toBeTruthy();
  });

  it('hides the CTA button when no buttonLabel is supplied', () => {
    const { queryByRole } = render(<ConversationsEmptyState description="..." icon={<span />} title="Empty" />);
    expect(queryByRole('button')).toBeNull();
  });

  it('renders the CTA button and fires onAction when both props are supplied', async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    const { getByRole } = render(
      <ConversationsEmptyState
        buttonLabel="Start a chat"
        description="..."
        icon={<span />}
        onAction={onAction}
        title="Empty"
      />
    );
    await user.click(getByRole('button', { name: 'Start a chat' }));
    expect(onAction).toHaveBeenCalled();
  });
});
