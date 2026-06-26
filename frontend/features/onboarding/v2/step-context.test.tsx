import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { StepContext } from './step-context';

describe('StepContext', () => {
  it('renders the heading + Open ChatGPT link + textarea', () => {
    const { getByRole, getByPlaceholderText } = render(
      <StepContext onContinue={vi.fn()} onPatch={vi.fn()} onSkip={vi.fn()} profile={{}} />
    );
    expect(getByRole('heading', { name: /Let's give your agent some context/ })).toBeTruthy();
    expect(getByRole('link', { name: /Open ChatGPT/ })).toBeTruthy();
    expect(getByPlaceholderText("Paste ChatGPT's response here...")).toBeTruthy();
  });

  it('patches profile.chatgptContext when typing into the textarea', async () => {
    const onPatch = vi.fn();
    const user = userEvent.setup();
    const { getByPlaceholderText } = render(
      <StepContext onContinue={vi.fn()} onPatch={onPatch} onSkip={vi.fn()} profile={{}} />
    );
    const textarea = getByPlaceholderText("Paste ChatGPT's response here...");
    // `user.click` focuses the textarea, then `user.paste` fires one
    // synthetic paste event with the full string — matches the
    // product's intended UX (user copies from ChatGPT, pastes here)
    // and avoids the per-keystroke fire of `user.type` against an
    // uncontrolled textarea.
    await user.click(textarea);
    await user.paste('pasted blob');
    expect(onPatch).toHaveBeenCalledWith({ chatgptContext: 'pasted blob' });
  });

  it('fires onContinue + onSkip from their respective controls', async () => {
    const onContinue = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();
    const { getByText } = render(
      <StepContext onContinue={onContinue} onPatch={vi.fn()} onSkip={onSkip} profile={{}} />
    );
    await user.click(getByText('Continue'));
    await user.click(getByText('Skip for now'));
    expect(onContinue).toHaveBeenCalled();
    expect(onSkip).toHaveBeenCalled();
  });
});
