import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SectionHeader } from './SectionHeader';

describe('SectionHeader', () => {
  it('renders the section label inside an <li>', () => {
    const { getByText, container } = render(<SectionHeader label="Today" />);
    expect(getByText('Today')).toBeTruthy();
    expect(container.querySelector('li')).toBeTruthy();
  });
});
