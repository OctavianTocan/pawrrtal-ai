'use client';

import type * as React from 'react';
import { useId } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { PersonalizationProfile } from '@/lib/personalization/storage';
import { cn } from '@/lib/utils';
import { OnboardingShell } from './onboarding-shell';

/** Goal chips shown at the bottom of step 1. */
const GOAL_CHIPS = [
  'SEO / AEO',
  'Generate Leads',
  'Nurture Leads',
  'Run My Outbound',
  'Handle Support',
  'Personal Assistant',
  'Run Ads',
  'Writing',
] as const;

/** Props for {@link StepIdentity}. */
export interface StepIdentityProps {
  profile: PersonalizationProfile;
  onPatch: (patch: Partial<PersonalizationProfile>) => void;
  onContinue: () => void;
}

/**
 * Step 1 — basic identity capture.
 *
 * Fields: name, company website, linkedin (optional), role, goal chips.
 * Continues regardless of completeness; we treat onboarding as a soft
 * gate, not a wall.
 */
export function StepIdentity({ profile, onPatch, onContinue }: StepIdentityProps): React.JSX.Element {
  const goals = profile.goals ?? [];
  const fieldId = useId();
  const nameId = `${fieldId}-name`;
  const companyWebsiteId = `${fieldId}-company-website`;
  const linkedinId = `${fieldId}-linkedin`;
  const roleId = `${fieldId}-role`;

  const toggleGoal = (goal: string): void => {
    const next = goals.includes(goal) ? goals.filter((g) => g !== goal) : [...goals, goal];
    onPatch({ goals: next });
  };

  return (
    <OnboardingShell
      footer={
        <Button
          className="h-11 w-full max-w-sm cursor-pointer rounded-control bg-foreground px-8 text-sm font-semibold text-background shadow-none hover:bg-foreground/90 hover:shadow-minimal"
          onClick={onContinue}
          size="lg"
          type="button"
        >
          Continue →
        </Button>
      }
      subtitle="We'll use this to personalize your agent."
      title="Let's get to know you"
    >
      <Field htmlFor={nameId} label="Your name">
        <Input
          id={nameId}
          onChange={(event) => onPatch({ name: event.target.value })}
          placeholder="Your name"
          value={profile.name ?? ''}
        />
      </Field>
      <Field htmlFor={companyWebsiteId} label="Company website">
        <Input
          id={companyWebsiteId}
          onChange={(event) => onPatch({ companyWebsite: event.target.value })}
          placeholder="https://yourcompany.com"
          value={profile.companyWebsite ?? ''}
        />
      </Field>
      <Field helper="Optional — helps personalize your agent" htmlFor={linkedinId} label="Your LinkedIn profile">
        <Input
          id={linkedinId}
          onChange={(event) => onPatch({ linkedin: event.target.value })}
          placeholder="https://linkedin.com/in/yourname"
          value={profile.linkedin ?? ''}
        />
      </Field>
      <Field htmlFor={roleId} label="Your role">
        <Input
          id={roleId}
          onChange={(event) => onPatch({ role: event.target.value })}
          placeholder="e.g. Founder, Engineering"
          value={profile.role ?? ''}
        />
      </Field>
      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-foreground">What do you want to accomplish?</span>
        <div className="flex flex-wrap gap-2">
          {GOAL_CHIPS.map((goal) => {
            const isOn = goals.includes(goal);
            return (
              <button
                className={cn(
                  'cursor-pointer rounded-full border px-3 py-1.5 text-sm transition-colors',
                  isOn
                    ? 'border-foreground bg-foreground text-background'
                    : 'border-foreground/15 bg-foreground/[0.03] text-foreground hover:bg-foreground/[0.06]'
                )}
                key={goal}
                onClick={() => toggleGoal(goal)}
                type="button"
              >
                {goal}
              </button>
            );
          })}
        </div>
      </div>
    </OnboardingShell>
  );
}

/** Small label-over-input wrapper used throughout step 1. */
function Field({
  label,
  htmlFor,
  helper,
  children,
}: {
  label: React.ReactNode;
  htmlFor: string;
  helper?: React.ReactNode;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-foreground" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {helper ? <span className="text-sm text-muted-foreground">{helper}</span> : null}
    </div>
  );
}
