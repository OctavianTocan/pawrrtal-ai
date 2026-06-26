import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Loader } from './loader';

describe('Loader', () => {
  it('renders with default size', () => {
    const { container } = render(<Loader />);
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('honors a custom size prop', () => {
    const { container } = render(<Loader size={24} />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('24');
    expect(svg?.getAttribute('height')).toBe('24');
  });

  it('forwards className', () => {
    const { container } = render(<Loader className="loader-x" />);
    expect(container.firstElementChild?.className.includes('loader-x')).toBe(true);
  });
});
