/**
 * Tests for interactive artifact widgets and the surrounding interaction
 * context plumbing.
 *
 * Strategy: render an `<ArtifactCard>` (the surface a user actually sees),
 * open the dialog, interact with each widget, and assert the handler we
 * installed via `<ArtifactInteractionProvider>` receives the right payload.
 * That exercises the full json-render → catalog → renderer path, not just
 * a renderer in isolation.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatArtifactInteractionPayload, ChatArtifactPayload } from '@/lib/types';
import { ArtifactCard } from './ArtifactCard';
import { ArtifactInteractionProvider } from './interaction-context';

afterEach(cleanup);

function buildArtifact(elements: ChatArtifactPayload['spec']['elements']): ChatArtifactPayload {
  return {
    id: 'art_test_001',
    title: 'Interactive demo',
    tool_use_id: 'tu_1',
    spec: { root: 'page', elements },
  };
}

function renderWithProvider(artifact: ChatArtifactPayload, handler: (payload: ChatArtifactInteractionPayload) => void) {
  return render(
    <ArtifactInteractionProvider handler={handler}>
      <ArtifactCard artifact={artifact} />
    </ArtifactInteractionProvider>
  );
}

function openCard(): void {
  fireEvent.click(screen.getByRole('button', { name: /open artifact/i }));
}

describe('ActionButton', () => {
  const artifact = buildArtifact({
    page: { type: 'Page', props: { title: 'demo', accent: 'cat' }, children: ['btn'] },
    btn: {
      type: 'ActionButton',
      props: { label: 'Continue', actionId: 'accept_plan', style: 'primary' },
    },
  });

  it('dispatches a new_turn interaction with the button label as both label and value', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({
      artifactId: 'art_test_001',
      actionId: 'accept_plan',
      label: 'Continue',
      value: 'Continue',
      mode: 'new_turn',
    });
  });

  it('renders disabled when no interaction provider is installed', () => {
    render(<ArtifactCard artifact={artifact} />);
    openCard();
    const button = screen.getByRole('button', { name: 'Continue' });
    expect(button).toBeDisabled();
  });
});

describe('ChoiceGroup', () => {
  const artifact = buildArtifact({
    page: { type: 'Page', props: { title: 'demo', accent: 'cat' }, children: ['choice'] },
    choice: {
      type: 'ChoiceGroup',
      props: {
        actionId: 'pick_severity',
        prompt: 'How severe?',
        multi: false,
        options: [
          { value: 'low', label: 'Low' },
          { value: 'high', label: 'High' },
        ],
      },
    },
  });

  it('submits the selected radio value as the label and key', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    fireEvent.click(screen.getByLabelText('High'));
    fireEvent.click(screen.getByRole('button', { name: /submit choice/i }));

    expect(handler).toHaveBeenCalledWith({
      artifactId: 'art_test_001',
      actionId: 'pick_severity',
      label: 'High',
      value: 'high',
      mode: 'new_turn',
    });
  });

  it('submits an array of option keys for multi-select', () => {
    const multiArtifact = buildArtifact({
      page: { type: 'Page', props: { title: 'demo', accent: 'cat' }, children: ['choice'] },
      choice: {
        type: 'ChoiceGroup',
        props: {
          actionId: 'pick_tags',
          prompt: null,
          multi: true,
          options: [
            { value: 'a', label: 'Apple' },
            { value: 'b', label: 'Banana' },
            { value: 'c', label: 'Cherry' },
          ],
        },
      },
    });

    const handler = vi.fn();
    renderWithProvider(multiArtifact, handler);
    openCard();

    fireEvent.click(screen.getByLabelText('Apple'));
    fireEvent.click(screen.getByLabelText('Cherry'));
    fireEvent.click(screen.getByRole('button', { name: /submit selection/i }));

    expect(handler).toHaveBeenCalledTimes(1);
    const call = handler.mock.calls[0]?.[0] as ChatArtifactInteractionPayload;
    expect(call.actionId).toBe('pick_tags');
    expect(call.value).toEqual(['a', 'c']);
    expect(call.label).toBe('Apple, Cherry');
  });

  it('disables submit until at least one option is picked', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();
    expect(screen.getByRole('button', { name: /submit choice/i })).toBeDisabled();
  });
});

describe('TextField', () => {
  const artifact = buildArtifact({
    page: { type: 'Page', props: { title: 'demo', accent: 'cat' }, children: ['tf'] },
    tf: {
      type: 'TextField',
      props: {
        actionId: 'describe_bug',
        label: 'Describe the bug',
        placeholder: null,
        multiline: false,
        submitLabel: 'Send',
      },
    },
  });

  it('submits trimmed text on Enter for single-line input', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    const input = screen.getByLabelText('Describe the bug');
    fireEvent.change(input, { target: { value: '  crash on submit  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handler).toHaveBeenCalledWith({
      artifactId: 'art_test_001',
      actionId: 'describe_bug',
      label: 'crash on submit',
      value: 'crash on submit',
      mode: 'new_turn',
    });
  });

  it('does not submit on Enter when the field is empty', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    const input = screen.getByLabelText('Describe the bug');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handler).not.toHaveBeenCalled();
  });
});

describe('NumberField', () => {
  const artifact = buildArtifact({
    page: { type: 'Page', props: { title: 'demo', accent: 'cat' }, children: ['n'] },
    n: {
      type: 'NumberField',
      props: {
        actionId: 'pick_count',
        label: 'How many?',
        min: 1,
        max: 5,
        step: 1,
        defaultValue: 3,
        kind: 'slider',
        submitLabel: 'Confirm',
      },
    },
  });

  it('submits the selected number with a human-readable label', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    expect(handler).toHaveBeenCalledWith({
      artifactId: 'art_test_001',
      actionId: 'pick_count',
      label: 'How many?: 3',
      value: 3,
      mode: 'new_turn',
    });
  });

  it('clamps a user-entered value above the max', () => {
    const handler = vi.fn();
    renderWithProvider(artifact, handler);
    openCard();

    const slider = screen.getByLabelText(/how many/i);
    fireEvent.change(slider, { target: { value: '99' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    const call = handler.mock.calls[0]?.[0] as ChatArtifactInteractionPayload;
    expect(call.value).toBe(5);
  });
});
