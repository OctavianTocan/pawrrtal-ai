'use client';

import { ModalDescription, ModalHeader } from '@octavian-tocan/react-overlay';
import { Pencil } from 'lucide-react';
import { useId } from 'react';
import { AppDialog } from '@/components/ui/app-dialog';
import { AppDialogFooter } from '@/components/ui/app-dialog-footer';
import { AppFormRow } from '@/components/ui/app-form-row';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface ConversationRenameDialogProps {
  /** Whether the dialog is open. */
  isOpen: boolean;
  /** Whether the rename mutation is currently pending. */
  isPending: boolean;
  /** The current draft title being edited. */
  draftTitle: string;
  /** Called when the draft title changes. */
  onDraftTitleChange: (title: string) => void;
  /** Called when the dialog open state changes. */
  onOpenChange: (open: boolean) => void;
  /** Called when the form is submitted. */
  onSubmit: () => void;
}

/**
 * Dialog for renaming a conversation.
 *
 * Renders as a centered Modal on desktop and a draggable BottomSheet on mobile
 * via {@link AppDialog}. Disables the Save button while the rename
 * mutation is pending or if the title is empty.
 *
 * @returns The rename dialog rendered through the project overlay primitive.
 */
export function ConversationRenameDialog({
  isOpen,
  isPending,
  draftTitle,
  onDraftTitleChange,
  onOpenChange,
  onSubmit,
}: ConversationRenameDialogProps): React.JSX.Element {
  const formId = useId();
  const titleInputId = useId();

  const header = (
    <ModalHeader icon={<Pencil aria-hidden className="size-4 text-white" />} title="Rename Conversation" />
  );

  const footer = (
    <AppDialogFooter>
      <Button disabled={isPending} onClick={() => onOpenChange(false)} type="button" variant="outline">
        Cancel
      </Button>
      <Button disabled={!draftTitle.trim() || isPending} form={formId} type="submit">
        {isPending ? 'Saving...' : 'Save'}
      </Button>
    </AppDialogFooter>
  );

  return (
    <AppDialog
      open={isOpen}
      onDismiss={() => onOpenChange(false)}
      ariaLabel="Rename Conversation"
      footer={footer}
      header={header}
      showDismissButton
      sheetTitle="Rename Conversation"
      size="md"
      testId="conversation-rename-dialog"
    >
      <form action={onSubmit} className="grid gap-4 text-foreground" id={formId}>
        <ModalDescription className="text-muted-foreground">
          Update the sidebar title for this conversation.
        </ModalDescription>
        <AppFormRow htmlFor={titleInputId} label="Conversation title" labelVisibility="sr-only">
          <Input
            id={titleInputId}
            maxLength={255}
            onChange={(event) => onDraftTitleChange(event.target.value)}
            placeholder="Conversation title"
            value={draftTitle}
          />
        </AppFormRow>
      </form>
    </AppDialog>
  );
}
