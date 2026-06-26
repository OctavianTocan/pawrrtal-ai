import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OnboardingShell } from './onboarding-shell';

describe('OnboardingShell', () => {
  it('renders the title heading + body content', () => {
    const { getByRole, getByText } = render(
      <OnboardingShell title="Step One">
        <p>body</p>
      </OnboardingShell>
    );
    expect(getByRole('heading', { name: 'Step One' })).toBeTruthy();
    expect(getByText('body')).toBeTruthy();
  });

  it('renders the subtitle when supplied', () => {
    const { getByText } = render(
      <OnboardingShell subtitle="A helper line" title="Step One">
        body
      </OnboardingShell>
    );
    expect(getByText('A helper line')).toBeTruthy();
  });

  it('renders the optional footer slot', () => {
    const { getByText } = render(
      <OnboardingShell footer={<button type="button">Save step</button>} title="Step One">
        body
      </OnboardingShell>
    );
    expect(getByText('Save step')).toBeTruthy();
  });
});
