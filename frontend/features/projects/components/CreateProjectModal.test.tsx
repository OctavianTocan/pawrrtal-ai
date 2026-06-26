import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CreateProjectModal } from './CreateProjectModal';

const noop = (): void => {
  /* */
};

describe('CreateProjectModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <CreateProjectModal isPending={false} onDismiss={noop} onSubmit={noop} open={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the heading + helper line + Create button when open', () => {
    const { getByRole, getByText } = render(
      <CreateProjectModal isPending={false} onDismiss={noop} onSubmit={noop} open />
    );
    expect(getByRole('heading', { name: 'Create project' })).toBeTruthy();
    expect(getByText(/Projects keep chats/i)).toBeTruthy();
    expect(getByRole('button', { name: 'Create project' })).toBeTruthy();
  });

  it('disables Create when the input is empty', () => {
    const { getByRole } = render(<CreateProjectModal isPending={false} onDismiss={noop} onSubmit={noop} open />);
    const button = getByRole('button', { name: 'Create project' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('fires onSubmit with the trimmed name when the form is submitted', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    const { getByLabelText, getByRole } = render(
      <CreateProjectModal isPending={false} onDismiss={noop} onSubmit={onSubmit} open />
    );
    const input = getByLabelText('Project name');
    await user.click(input);
    await user.paste('  Copenhagen Trip  ');
    await user.click(getByRole('button', { name: 'Create project' }));
    expect(onSubmit).toHaveBeenCalledWith('Copenhagen Trip');
  });

  it('fires onDismiss when Cancel is clicked', async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    const { getByRole } = render(<CreateProjectModal isPending={false} onDismiss={onDismiss} onSubmit={noop} open />);
    await user.click(getByRole('button', { name: 'Cancel' }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('shows the loading label while pending and disables submit', () => {
    const { getByRole } = render(<CreateProjectModal isPending onDismiss={noop} onSubmit={noop} open />);
    const button = getByRole('button', { name: 'Creating...' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });
});
