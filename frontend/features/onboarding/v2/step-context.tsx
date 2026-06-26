'use client';

import { ArrowRight } from 'lucide-react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { PersonalizationProfile } from '@/lib/personalization/storage';
import { OnboardingShell } from './onboarding-shell';

/** Props for {@link StepContext}. */
export interface StepContextProps {
  profile: PersonalizationProfile;
  onPatch: (patch: Partial<PersonalizationProfile>) => void;
  onContinue: () => void;
  onSkip: () => void;
}

/**
 * Step 2 — paste-in context.
 *
 * Cosmetic for now. The "Open ChatGPT" button is a real link; the
 * pasted blob is stored as `chatgptContext` for later system-prompt
 * threading.
 */
export function StepContext({ profile, onPatch, onContinue, onSkip }: StepContextProps): React.JSX.Element {
  return (
    <OnboardingShell
      footer={
        <>
          <Button
            className="h-11 w-full max-w-sm cursor-pointer rounded-control bg-foreground px-8 text-sm font-semibold text-background shadow-none hover:bg-foreground/90 hover:shadow-minimal"
            onClick={onContinue}
            size="lg"
            type="button"
          >
            Continue
            <ArrowRight aria-hidden="true" className="ml-1 size-4" />
          </Button>
          <button
            className="cursor-pointer text-sm text-muted-foreground hover:text-foreground"
            onClick={onSkip}
            type="button"
          >
            Skip for now
          </button>
        </>
      }
      subtitle="We'll use ChatGPT's knowledge about you to personalize your agent. This takes 30 seconds."
      title="Let's give your agent some context about you"
    >
      <a
        className="flex items-center justify-center gap-2 rounded-[10px] border border-foreground/15 bg-foreground/[0.03] px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-foreground/[0.06]"
        href="https://chat.openai.com"
        rel="noopener noreferrer"
        target="_blank"
      >
        Open ChatGPT
        <ArrowRight aria-hidden="true" className="size-4" />
      </a>
      <Textarea
        className="min-h-44 resize-y bg-foreground/[0.02]"
        onChange={(event) => onPatch({ chatgptContext: event.target.value })}
        placeholder="Paste ChatGPT's response here..."
        value={profile.chatgptContext ?? ''}
      />
      <p className="text-center text-sm text-muted-foreground">
        Don't have ChatGPT? Skip this step. You can always add context later.
      </p>
    </OnboardingShell>
  );
}
