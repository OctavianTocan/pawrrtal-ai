import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Image } from './image';

describe('Image', () => {
  it('renders an <img> with a data URL pointing at the base64 payload', () => {
    const { container } = render(
      <Image base64="aGVsbG8=" uint8Array={new Uint8Array([1])} mediaType="image/png" alt="hello" />
    );
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('data:image/png;base64,aGVsbG8=');
    expect(img?.getAttribute('alt')).toBe('hello');
  });

  it('forwards a custom className alongside the defaults', () => {
    const { container } = render(
      <Image base64="aGVsbG8=" uint8Array={new Uint8Array([1])} mediaType="image/png" className="custom-img" alt="" />
    );
    expect(container.querySelector('img')?.className).toContain('custom-img');
  });
});
