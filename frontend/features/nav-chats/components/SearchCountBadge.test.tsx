import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SearchCountBadge } from './SearchCountBadge';

describe('SearchCountBadge', () => {
  it('renders the supplied count', () => {
    const { getByText } = render(<SearchCountBadge count={7} isSelected={false} />);
    expect(getByText('7')).toBeTruthy();
  });

  it('exposes a "Matches found" tooltip', () => {
    const { container } = render(<SearchCountBadge count={1} isSelected={false} />);
    expect(container.querySelector('span[title="Matches found"]')).toBeTruthy();
  });

  it('switches palette when isSelected toggles', () => {
    const { container: unselected } = render(<SearchCountBadge count={3} isSelected={false} />);
    const { container: selected } = render(<SearchCountBadge count={3} isSelected />);
    const unselectedClass = unselected.firstElementChild?.className ?? '';
    const selectedClass = selected.firstElementChild?.className ?? '';
    expect(unselectedClass).not.toBe(selectedClass);
  });
});
