'use client';

import { ModalDescription, ModalHeader } from '@octavian-tocan/react-overlay';
import { AlertTriangle } from 'lucide-react';
import { AppDialog } from '@/components/ui/app-dialog';
import { AppDialogFooter } from '@/components/ui/app-dialog-footer';
import { Button } from '@/components/ui/button';

interface ConversationDeleteDialogProps {
  /** Whether the dialog is open. */
  isOpen: boolean;
  /** Whether the delete mutation is currently pending. */
  isPending: boolean;
  /** Called when the dialog open state changes. */
  onOpenChange: (open: boolean) => void;
  /** Called when the user confirms deletion. */
  onConfirm: () => void;
}

/**
 * Destructive confirmation dialog for deleting a conversation.
 *
 * Renders as a centered Modal on desktop and a draggable BottomSheet on mobile
 * via {@link AppDialog}. Both actions are disabled while the delete
 * mutation is in flight so the user can't double-fire.
 *
 * @returns The delete confirmation rendered through the project overlay primitive.
 */
export function ConversationDeleteDialog({
  isOpen,
  isPending,
  onOpenChange,
  onConfirm,
}: ConversationDeleteDialogProps): React.JSX.Element {
  const header = (
    <ModalHeader icon={<AlertTriangle aria-hidden className="size-4 text-white" />} title="Delete Conversation?" />
  );

  const footer = (
    <AppDialogFooter>
      <Button disabled={isPending} onClick={() => onOpenChange(false)} type="button" variant="outline">
        Cancel
      </Button>
      <Button
        disabled={isPending}
        onClick={(event) => {
          event.preventDefault();
          onConfirm();
        }}
        type="button"
        variant="destructive"
      >
        {isPending ? 'Deleting...' : 'Delete'}
      </Button>
    </AppDialogFooter>
  );

  return (
    <AppDialog
      open={isOpen}
      onDismiss={() => {
        if (!isPending) {
          onOpenChange(false);
        }
      }}
      closeOnOverlayClick={!isPending}
      closeOnEscape={!isPending}
      ariaLabel="Delete Conversation"
      footer={footer}
      header={header}
      showDismissButton={!isPending}
      sheetTitle="Delete Conversation"
      size="sm"
      testId="conversation-delete-dialog"
    >
      <ModalDescription className="text-muted-foreground">
        This removes the conversation from your sidebar. This action cannot be undone.
      </ModalDescription>
    </AppDialog>
  );
}
