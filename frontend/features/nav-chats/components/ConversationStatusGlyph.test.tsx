import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConversationStatusGlyph } from './ConversationStatusGlyph';
import { STATUS_SUBMENU } from './conversation-status-data';

describe('ConversationStatusGlyph', () => {
  it('renders the todo glyph in the info color', () => {
    const { container } = render(<ConversationStatusGlyph status="todo" />);
    expect(container.querySelector('.text-info')).toBeTruthy();
  });

  it('renders the in_progress glyph in the warning color', () => {
    const { container } = render(<ConversationStatusGlyph status="in_progress" />);
    expect(container.querySelector('.text-warning')).toBeTruthy();
  });

  it('renders the done glyph in the success color', () => {
    const { container } = render(<ConversationStatusGlyph status="done" />);
    expect(container.querySelector('.text-success')).toBeTruthy();
  });

  it('renders a muted neutral glyph when status is null', () => {
    const { container } = render(<ConversationStatusGlyph status={null} />);
    expect(container.querySelector('[class*="muted-foreground"]')).toBeTruthy();
  });
});

describe('STATUS_SUBMENU', () => {
  it('exposes a row per status state including the no-status reset row', () => {
    const ids = STATUS_SUBMENU.map((entry) => entry.id);
    expect(ids).toContain('todo');
    expect(ids).toContain('in_progress');
    expect(ids).toContain('done');
    expect(ids).toContain(null);
  });

  it('exposes a unique label per row', () => {
    const labels = STATUS_SUBMENU.map((entry) => entry.label);
    expect(new Set(labels).size).toBe(labels.length);
  });
});
