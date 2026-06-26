import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PlaceholderSection } from './PlaceholderSection';

describe('PlaceholderSection', () => {
  it('renders the supplied title heading', () => {
    const { getByRole } = render(<PlaceholderSection title="Browser use" />);
    expect(getByRole('heading', { name: 'Browser use' })).toBeTruthy();
  });

  it('shows the standard "coming soon" copy', () => {
    const { getByText } = render(<PlaceholderSection title="Git" />);
    expect(getByText('This section is coming soon.')).toBeTruthy();
  });
});
