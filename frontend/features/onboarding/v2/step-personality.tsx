'use client';

import { Check } from 'lucide-react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import type { PersonalityId, PersonalizationProfile } from '@/lib/personalization/storage';
import { PERSONALITY_OPTIONS } from '@/lib/personalization/storage';
import { cn } from '@/lib/utils';
import { OnboardingShell } from './onboarding-shell';

/** Props for {@link StepPersonality}. */
export interface StepPersonalityProps {
  profile: PersonalizationProfile;
  onPatch: (patch: Partial<PersonalizationProfile>) => void;
  onContinue: () => void;
}

/**
 * Step 3 — pick a default personality preset.
 *
 * Cards mirror the reference. Selected card gets a filled check in the
 * top-right corner. The chosen ID is persisted; later wired into the
 * agent factory's system prompt.
 */
export function StepPersonality({ profile, onPatch, onContinue }: StepPersonalityProps): React.JSX.Element {
  const selected: PersonalityId = profile.personality ?? PERSONALITY_OPTIONS[0].id;

  return (
    <OnboardingShell
      footer={
        <Button
          className="h-11 w-full max-w-sm cursor-pointer rounded-control bg-foreground px-8 font-semibold text-background text-sm shadow-none hover:bg-foreground/90 hover:shadow-minimal"
          onClick={onContinue}
          size="lg"
          type="button"
        >
          Save personality
        </Button>
      }
      subtitle="Pick a personality."
      title="How should your agent communicate?"
    >
      <div className="flex flex-col gap-2.5">
        {PERSONALITY_OPTIONS.map((option) => {
          const isSelected = option.id === selected;
          return (
            <button
              aria-pressed={isSelected}
              className={cn(
                'flex w-full cursor-pointer flex-col gap-1.5 rounded-[12px] border px-4 py-3 text-left transition-colors',
                isSelected
                  ? 'border-foreground bg-foreground/[0.04]'
                  : 'border-foreground/10 bg-foreground/[0.02] hover:bg-foreground/[0.04]'
              )}
              key={option.id}
              onClick={() => onPatch({ personality: option.id })}
              type="button"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-semibold text-foreground text-sm">{option.label}</span>
                <span
                  aria-hidden="true"
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full border',
                    isSelected ? 'border-foreground bg-foreground text-background' : 'border-foreground/15'
                  )}
                >
                  {isSelected ? <Check className="size-3" strokeWidth={3} /> : null}
                </span>
              </div>
              <p className="text-muted-foreground text-sm">{option.summary}</p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {option.traits.map((trait) => (
                  <span
                    className="rounded-full bg-foreground/[0.06] px-2 py-0.5 text-muted-foreground text-xs"
                    key={trait}
                  >
                    {trait}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>
    </OnboardingShell>
  );
}
