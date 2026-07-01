import { ArrowLeft02Icon, FolderCheckIcon, FolderOpenIcon } from '@hugeicons/core-free-icons';
import { HugeiconsIcon } from '@hugeicons/react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { DialogDescription, DialogHeader } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/** Props for the existing-folder onboarding step. */
export interface OnboardingLocalWorkspaceStepProps {
  /** Input id used by the hidden folder picker and label. */
  folderInputId: string;
  /** Ref for imperatively opening the browser folder picker. */
  folderInputRef: React.RefObject<HTMLInputElement | null>;
  /** Human-readable selected folder label. */
  folderLabel: string | null;
  /** Handles changes from the hidden folder picker input. */
  onFolderChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  /** Opens the hidden folder picker input. */
  onSelectFolderClick: () => void;
  /** Returns to the workspace option step. */
  onBack: () => void;
  /** Finishes or dismisses onboarding. */
  onFinish: () => void;
}

/**
 * Cosmetic local workspace step — folder selection is UI-only until backend support exists.
 */
export function OnboardingLocalWorkspaceStep({
  folderInputId,
  folderInputRef,
  folderLabel,
  onFolderChange,
  onSelectFolderClick,
  onBack,
  onFinish,
}: OnboardingLocalWorkspaceStepProps): React.JSX.Element {
  const isFolderSelected = Boolean(folderLabel);

  return (
    <section className="popover-styled onboarding-panel flex w-full max-w-[32rem] select-none flex-col gap-6 rounded-surface-lg border border-border bg-background/95 p-6 text-foreground shadow-modal-small sm:p-7">
      <button
        aria-label="Back to workspace options"
        className="-ml-1 flex h-8 w-fit cursor-pointer items-center gap-2 rounded-lg px-2 text-muted-foreground text-sm transition-[background-color,color] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] hover:bg-foreground/[0.045] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 active:bg-foreground/[0.035]"
        onClick={onBack}
        type="button"
      >
        <HugeiconsIcon aria-hidden="true" icon={ArrowLeft02Icon} size={16} strokeWidth={1.7} />
        <span>Back</span>
      </button>

      <DialogHeader className="gap-2 text-left">
        <div
          aria-hidden="true"
          className="text-balance font-semibold text-[1.375rem] text-foreground leading-tight tracking-tight"
        >
          Choose folder
        </div>
        <DialogDescription className="max-w-[26rem] text-[0.9375rem] text-muted-foreground leading-relaxed">
          Pick the folder Pawrrtal can use as this workspace.
        </DialogDescription>
      </DialogHeader>

      {/*
        Cosmetic folder picker only — full workspace paths / persistence are future work.
      */}
      <Label className="sr-only" htmlFor={folderInputId}>
        Workspace folder
      </Label>
      <input
        className="sr-only"
        id={folderInputId}
        multiple
        onChange={onFolderChange}
        ref={folderInputRef}
        tabIndex={-1}
        type="file"
        {...({
          webkitdirectory: '',
          directory: '',
        } as React.InputHTMLAttributes<HTMLInputElement>)}
      />

      <div
        className={cn(
          'flex min-h-[6.75rem] w-full select-none items-center gap-4 rounded-lg px-4 text-left ring-1',
          isFolderSelected ? 'bg-foreground/[0.045] shadow-minimal ring-border' : 'bg-foreground/[0.025] ring-border'
        )}
      >
        <span
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-lg ring-1 transition-colors duration-150',
            isFolderSelected
              ? 'bg-foreground/[0.09] text-foreground ring-border'
              : 'bg-foreground/[0.04] text-muted-foreground ring-border'
          )}
        >
          {isFolderSelected ? (
            <HugeiconsIcon aria-hidden="true" icon={FolderCheckIcon} size={20} strokeWidth={1.7} />
          ) : (
            <HugeiconsIcon aria-hidden="true" icon={FolderOpenIcon} size={20} strokeWidth={1.7} />
          )}
        </span>
        <span aria-live="polite" className="min-w-0 flex-1">
          <span className="block truncate font-medium text-[0.9375rem] text-foreground">
            {folderLabel ?? 'Select a workspace folder'}
          </span>
          <span className="mt-1 block text-muted-foreground text-sm leading-5">
            {isFolderSelected
              ? 'Ready to open as your workspace.'
              : 'Browse your computer and choose the folder to use.'}
          </span>
        </span>
        <button
          className="inline-flex shrink-0 cursor-pointer rounded-lg bg-foreground/[0.045] px-3 py-2 font-medium text-foreground text-sm ring-1 ring-border transition-[background-color,color] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] hover:bg-foreground/[0.07] focus-visible:ring-2 focus-visible:ring-ring/45"
          onClick={onSelectFolderClick}
          type="button"
        >
          Browse
        </button>
      </div>

      <Button
        className="h-10 w-full cursor-pointer rounded-lg bg-foreground font-semibold text-background text-sm shadow-none transition-[background-color,box-shadow] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] hover:bg-foreground/90 hover:shadow-minimal active:bg-foreground/80 disabled:cursor-not-allowed disabled:bg-foreground/[0.09] disabled:text-muted-foreground"
        disabled={!isFolderSelected}
        onClick={onFinish}
        type="button"
      >
        {isFolderSelected ? 'Open workspace' : 'Select a folder first'}
      </Button>
    </section>
  );
}
