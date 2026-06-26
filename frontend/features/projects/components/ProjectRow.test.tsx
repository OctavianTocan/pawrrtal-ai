import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CONVERSATION_DRAG_MIME } from '@/lib/conversations/drag';
import { ProjectRow } from './ProjectRow';

describe('ProjectRow', () => {
  function renderRow(overrides: Partial<React.ComponentProps<typeof ProjectRow>> = {}) {
    const props: React.ComponentProps<typeof ProjectRow> = {
      id: 'proj-1',
      name: 'portfolio',
      onClick: vi.fn(),
      onRename: vi.fn(),
      onConversationDrop: vi.fn(),
      ...overrides,
    };
    return { ...render(<ProjectRow {...props} />), props };
  }

  it('renders the folder icon + project name', () => {
    const { getByText } = renderRow();
    expect(getByText('portfolio')).toBeTruthy();
  });

  it('fires onClick when the body button is pressed', () => {
    const { getByText, props } = renderRow();
    fireEvent.click(getByText('portfolio'));
    expect(props.onClick).toHaveBeenCalled();
  });

  it('fires onRename and stops propagation when the pencil is clicked', () => {
    const { getByLabelText, props } = renderRow();
    fireEvent.click(getByLabelText('Rename portfolio'));
    expect(props.onRename).toHaveBeenCalled();
    expect(props.onClick).not.toHaveBeenCalled();
  });

  it('extracts the conversation ID from dataTransfer on drop', () => {
    const { container, props } = renderRow();
    // Drop handlers now live on the inner button (the row click target),
    // not the outer positioning wrapper — fires per the redesigned hit
    // area in DESIGN.md → Hit Targets.
    const wrapper = container.querySelector(
      `[data-project-id="proj-1"] button[aria-current], [data-project-id="proj-1"] button:not([aria-label*="Rename"])`
    );
    if (!wrapper) throw new Error('drop target not found');

    const types: string[] = [CONVERSATION_DRAG_MIME];
    const data: Record<string, string> = { [CONVERSATION_DRAG_MIME]: 'conv-42' };
    const dataTransfer = {
      get types() {
        return types;
      },
      getData: (key: string) => data[key] ?? '',
      dropEffect: 'none',
      setData: () => {
        /* noop */
      },
    } as unknown as DataTransfer;

    fireEvent.dragEnter(wrapper, { dataTransfer });
    fireEvent.dragOver(wrapper, { dataTransfer });
    fireEvent.drop(wrapper, { dataTransfer });

    expect(props.onConversationDrop).toHaveBeenCalledWith('conv-42');
  });

  it('ignores drops that do not carry a conversation payload', () => {
    const { container, props } = renderRow();
    // Drop handlers now live on the inner button (the row click target),
    // not the outer positioning wrapper — fires per the redesigned hit
    // area in DESIGN.md → Hit Targets.
    const wrapper = container.querySelector(
      `[data-project-id="proj-1"] button[aria-current], [data-project-id="proj-1"] button:not([aria-label*="Rename"])`
    );
    if (!wrapper) throw new Error('drop target not found');

    const dataTransfer = {
      types: ['text/plain'],
      getData: () => '',
      dropEffect: 'none',
      setData: () => {
        /* noop */
      },
    } as unknown as DataTransfer;

    fireEvent.drop(wrapper, { dataTransfer });
    expect(props.onConversationDrop).not.toHaveBeenCalled();
  });
});
