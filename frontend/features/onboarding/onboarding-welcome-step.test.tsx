import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Dialog } from '@/components/ui/dialog';
import { OnboardingWelcomeStep } from './onboarding-welcome-step';

const wrap = (node: React.ReactElement): React.ReactElement => (
  <Dialog open onOpenChange={() => undefined}>
    {node}
  </Dialog>
);

describe('OnboardingWelcomeStep', () => {
  it('renders the welcome heading + tagline + feature grid', () => {
    const { container } = render(wrap(<OnboardingWelcomeStep onContinue={() => undefined} />));
    expect(container.textContent).toContain('Welcome to Pawrrtal');
    expect(container.textContent).toContain('Edit spreadsheets');
    expect(container.textContent).toContain('Run agents');
  });

  it('fires onContinue when the primary CTA is clicked', async () => {
    const onContinue = vi.fn();
    const user = userEvent.setup();
    const { getByRole } = render(wrap(<OnboardingWelcomeStep onContinue={onContinue} />));
    await user.click(getByRole('button', { name: 'Get started' }));
    expect(onContinue).toHaveBeenCalled();
  });
});
