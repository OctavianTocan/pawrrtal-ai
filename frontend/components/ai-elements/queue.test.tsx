import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  QueueItem,
  QueueItemContent,
  QueueItemDescription,
  QueueItemFile,
  QueueItemImage,
  QueueItemIndicator,
  QueueList,
} from './queue';

describe('Queue primitives', () => {
  it('renders QueueList with QueueItem children', () => {
    const { getByText } = render(
      <QueueList>
        <QueueItem>
          <QueueItemIndicator>1</QueueItemIndicator>
          <QueueItemContent>
            <QueueItemDescription>Item description</QueueItemDescription>
          </QueueItemContent>
        </QueueItem>
      </QueueList>
    );
    expect(getByText('Item description')).toBeTruthy();
  });

  it('renders attachment file labels', () => {
    const { getByText } = render(<QueueItemFile>doc.pdf</QueueItemFile>);
    expect(getByText('doc.pdf')).toBeTruthy();
  });

  it('renders image attachments with the supplied src', () => {
    const { container } = render(<QueueItemImage alt="preview" src="https://example.com/x.png" />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('https://example.com/x.png');
    expect(img?.getAttribute('alt')).toBe('preview');
  });
});
