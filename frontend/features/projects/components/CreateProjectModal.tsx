'use client';

import { ModalHeader } from '@octavian-tocan/react-overlay';
import { FolderPlus, Lightbulb } from 'lucide-react';
import type * as React from 'react';
import { useId, useState } from 'react';
import { AppDialog } from '@/components/ui/app-dialog';
import { AppDialogCallout } from '@/components/ui/app-dialog-callout';
import { AppDialogFooter } from '@/components/ui/app-dialog-footer';
import { AppFormRow } from '@/components/ui/app-form-row';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

/** Props for {@link CreateProjectModal}. */
export interface CreateProjectModalProps {
  /** Whether the modal is currently visible. */
  open: boolean;
  /** True while the create mutation is in flight; disables the submit button. */
  isPending: boolean;
  /** Called when the user dismisses the modal (Cancel, ESC, backdrop). */
  onDismiss: () => void;
  /** Called with the trimmed project name when the user submits. */
  onSubmit: (name: string) => void;
}

/**
 * Project-creation modal. Mirrors the ChatGPT-style "Create project" sheet:
 * project name field with a placeholder, a one-line helper explaining what
 * projects are for, Cancel + Create project buttons.
 *
 * Uses {@link AppDialog} **`header`** / **`footer`** slots so
 * {@link BottomSheet} gets sticky chrome and {@link Modal} composes like the
 * react-overlay docs (`ModalHeader` + body + actions).
 *
 * The Create button is disabled while the field is empty so the user
 * never lands a project named "" (which would render as an empty row in
 * the sidebar). Submit fires via **`form`** association from the footer.
 */
export function CreateProjectModal({
  open,
  isPending,
  onDismiss,
  onSubmit,
}: CreateProjectModalProps): React.JSX.Element | null {
  const formId = useId();
  const inputId = useId();
  const [draft, setDraft] = useState('');

  if (!open) return null;

  const trimmed = draft.trim();
  const canSubmit = trimmed.length > 0 && !isPending;

  const handleClose = (): void => {
    setDraft('');
    onDismiss();
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmit) return;
    onSubmit(trimmed);
    setDraft('');
  };

  const header = <ModalHeader icon={<FolderPlus aria-hidden className="size-4 text-white" />} title="Create project" />;

  const footer = (
    <AppDialogFooter>
      <Button className="cursor-pointer" disabled={isPending} onClick={handleClose} type="button" variant="outline">
        Cancel
      </Button>
      <Button className="cursor-pointer" disabled={!canSubmit} form={formId} type="submit">
        {isPending ? 'Creating...' : 'Create project'}
      </Button>
    </AppDialogFooter>
  );

  return (
    <AppDialog
      ariaLabel="Create project"
      footer={footer}
      header={header}
      onDismiss={handleClose}
      open={open}
      sheetTitle="Create project"
      showDismissButton
      size="md"
    >
      <form className="flex flex-col gap-5 text-foreground" id={formId} onSubmit={handleSubmit}>
        <AppFormRow htmlFor={inputId} label="Project name">
          <Input
            id={inputId}
            maxLength={255}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Copenhagen Trip"
            value={draft}
          />
        </AppFormRow>

        <AppDialogCallout icon={<Lightbulb aria-hidden className="size-4 text-info" />} tone="info">
          <p className="leading-snug">
            Projects keep chats, files, and custom instructions in one place. Use them for ongoing work, or just to keep
            things tidy.
          </p>
        </AppDialogCallout>
      </form>
    </AppDialog>
  );
}
