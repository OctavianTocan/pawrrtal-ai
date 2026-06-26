import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Suggestion, Suggestions } from './suggestion';

describe('Suggestions', () => {
  it('renders the wrapped child suggestions', () => {
    const { getByText } = render(
      <Suggestions>
        <Suggestion suggestion="Hello" />
      </Suggestions>
    );
    expect(getByText('Hello')).toBeTruthy();
  });
});

describe('Suggestion', () => {
  it('renders the suggestion text as the button label by default', () => {
    const { getByRole } = render(<Suggestion suggestion="Hello" />);
    expect(getByRole('button', { name: 'Hello' })).toBeTruthy();
  });

  it('fires onClick with the suggestion text when activated', () => {
    const onClick = vi.fn();
    const { getByRole } = render(<Suggestion onClick={onClick} suggestion="Hi there" />);
    fireEvent.click(getByRole('button'));
    expect(onClick).toHaveBeenCalledWith('Hi there');
  });

  it('renders custom children instead of the default suggestion text', () => {
    const { getByRole } = render(
      <Suggestion suggestion="raw">
        <span>label</span>
      </Suggestion>
    );
    expect(getByRole('button', { name: 'label' })).toBeTruthy();
  });
});
