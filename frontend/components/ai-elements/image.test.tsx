import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Image } from './image';

describe('Image', () => {
  it('renders an <img> with a data URL pointing at the base64 payload', () => {
    const { container } = render(
      <Image alt="hello" base64="aGVsbG8=" mediaType="image/png" uint8Array={new Uint8Array([1])} />
    );
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('data:image/png;base64,aGVsbG8=');
    expect(img?.getAttribute('alt')).toBe('hello');
  });

  it('forwards a custom className alongside the defaults', () => {
    const { container } = render(
      <Image alt="" base64="aGVsbG8=" className="custom-img" mediaType="image/png" uint8Array={new Uint8Array([1])} />
    );
    expect(container.querySelector('img')?.className).toContain('custom-img');
  });
});
