import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Shimmer } from './shimmer';

describe('Shimmer', () => {
  it('renders the supplied text', () => {
    const { getByText } = render(<Shimmer>Loading&hellip;</Shimmer>);
    expect(getByText('Loading…')).toBeTruthy();
  });

  it('honors the `as` prop to render a different tag', () => {
    const { container } = render(<Shimmer as="span">x</Shimmer>);
    expect(container.querySelector('span')).toBeTruthy();
  });

  it('forwards className onto the rendered element', () => {
    const { container } = render(<Shimmer className="my-shimmer">x</Shimmer>);
    const root = container.firstElementChild as HTMLElement | null;
    expect(root?.className.includes('my-shimmer')).toBe(true);
  });
});
