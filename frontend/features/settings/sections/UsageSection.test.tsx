import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UsageSection } from './UsageSection';

describe('UsageSection', () => {
  it('renders the Usage heading + the three section headers', () => {
    const { getByRole, getByText } = render(<UsageSection />);
    expect(getByRole('heading', { name: 'Usage' })).toBeTruthy();
    expect(getByText('General usage limits')).toBeTruthy();
    expect(getByText('Credit')).toBeTruthy();
  });

  it('renders both Purchase + Settings credit buttons', () => {
    const { getByRole } = render(<UsageSection />);
    expect(getByRole('button', { name: 'Purchase' })).toBeTruthy();
    expect(getByRole('button', { name: 'Settings' })).toBeTruthy();
  });
});
