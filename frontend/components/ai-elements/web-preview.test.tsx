import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  WebPreview,
  WebPreviewBody,
  WebPreviewNavigation,
  WebPreviewNavigationButton,
  WebPreviewUrl,
} from './web-preview';

describe('WebPreview', () => {
  it('mounts the navigation + body inside a card surface', () => {
    const { container } = render(
      <WebPreview defaultUrl="https://example.com">
        <WebPreviewNavigation>
          <WebPreviewUrl />
        </WebPreviewNavigation>
        <WebPreviewBody src="https://example.com" />
      </WebPreview>
    );
    expect(container.querySelector('iframe')).toBeTruthy();
  });

  it('initializes the URL input with the supplied defaultUrl', () => {
    const { container } = render(
      <WebPreview defaultUrl="https://anthropic.com">
        <WebPreviewNavigation>
          <WebPreviewUrl />
        </WebPreviewNavigation>
      </WebPreview>
    );
    const input = container.querySelector('input') as HTMLInputElement | null;
    expect(input?.value).toBe('https://anthropic.com');
  });

  it('fires the navigation button onClick handler', () => {
    const onClick = vi.fn();
    const { getByRole } = render(
      <WebPreview defaultUrl="">
        <WebPreviewNavigation>
          <WebPreviewNavigationButton onClick={onClick}>Back</WebPreviewNavigationButton>
        </WebPreviewNavigation>
      </WebPreview>
    );
    fireEvent.click(getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });
});
