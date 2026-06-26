import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Message, MessageAction, MessageActions, MessageContent } from './message';

describe('Message', () => {
  it('applies the is-user marker class for user-role messages', () => {
    const { container } = render(<Message from="user">hi</Message>);
    expect(container.firstElementChild?.className).toContain('is-user');
  });

  it('applies the is-assistant marker class for assistant-role messages', () => {
    const { container } = render(<Message from="assistant">hi</Message>);
    expect(container.firstElementChild?.className).toContain('is-assistant');
  });

  it('renders children inside MessageContent', () => {
    const { getByText } = render(
      <Message from="assistant">
        <MessageContent>hello there</MessageContent>
      </Message>
    );
    expect(getByText('hello there')).toBeTruthy();
  });

  it('forwards onClick on MessageAction', () => {
    const onClick = vi.fn();
    const { getByRole } = render(
      <Message from="assistant">
        <MessageActions>
          <MessageAction label="copy" onClick={onClick}>
            Copy
          </MessageAction>
        </MessageActions>
      </Message>
    );
    fireEvent.click(getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });
});
