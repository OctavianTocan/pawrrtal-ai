import { FileSpreadsheetIcon, Folder01Icon, GlobeIcon, WorkflowSquare01Icon } from '@hugeicons/core-free-icons';
import { HugeiconsIcon } from '@hugeicons/react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { DialogDescription, DialogHeader } from '@/components/ui/dialog';

const FEATURE_ITEMS = [
  {
    icon: FileSpreadsheetIcon,
    title: 'Edit spreadsheets',
    description: 'Create, clean, and transform CSV and Excel files.',
  },
  {
    icon: GlobeIcon,
    title: 'Control your browser',
    description: 'Automate Chrome for repetitive web tasks.',
  },
  {
    icon: Folder01Icon,
    title: 'Organize files',
    description: 'Read, write, and manage files and folders.',
  },
  {
    icon: WorkflowSquare01Icon,
    title: 'Run agents',
    description: 'Turn repeatable work into durable commands.',
  },
] as const;

/** Props for the onboarding welcome step. */
export interface OnboardingWelcomeStepProps {
  /** Advances to the create-workspace step. */
  onContinue: () => void;
}

/** First onboarding screen: hero, feature grid, primary CTA. */
export function OnboardingWelcomeStep({ onContinue }: OnboardingWelcomeStepProps): React.JSX.Element {
  return (
    <section className="popover-styled onboarding-panel flex w-full max-w-[37rem] select-none flex-col gap-7 rounded-surface-lg border border-border bg-background/95 px-7 py-8 text-foreground shadow-modal-small sm:px-8 sm:py-9">
      <div className="flex flex-col gap-4 text-left">
        <DialogHeader className="gap-2 text-left">
          <div
            aria-hidden="true"
            className="text-balance font-semibold text-2xl text-foreground tracking-tight sm:text-[1.65rem]"
          >
            Welcome to Pawrrtal
          </div>
          <DialogDescription className="max-w-[30rem] text-[0.9375rem] text-muted-foreground leading-relaxed">
            Your computer, but it works for you.
          </DialogDescription>
        </DialogHeader>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FEATURE_ITEMS.map((item): React.JSX.Element => {
          const Icon = item.icon;

          return (
            <div
              className="flex min-h-[6rem] items-start gap-3 rounded-surface-lg bg-foreground/[0.025] p-4 ring-1 ring-border transition-[background-color,box-shadow] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] hover:bg-foreground/[0.04] hover:shadow-minimal"
              key={item.title}
            >
              <span
                aria-hidden="true"
                className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-surface-lg bg-foreground/[0.045] text-muted-foreground ring-1 ring-border"
              >
                <HugeiconsIcon aria-hidden="true" icon={Icon} size={20} strokeWidth={1.65} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold text-foreground text-sm">{item.title}</span>
                <span className="mt-1 block text-muted-foreground text-sm leading-snug">{item.description}</span>
              </span>
            </div>
          );
        })}
      </div>

      <Button
        className="h-11 w-full cursor-pointer rounded-control bg-foreground px-8 font-semibold text-background text-sm shadow-none transition-[background-color,box-shadow] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] hover:bg-foreground/90 hover:shadow-minimal active:bg-foreground/80"
        onClick={onContinue}
        size="lg"
        type="button"
      >
        Get started
      </Button>
    </section>
  );
}
