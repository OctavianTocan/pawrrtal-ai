/**
 * Menu item that opens the prompt input file chooser.
 *
 * @fileoverview AI Elements — prompt input add-attachment action subcomponent.
 */

'use client';

import { DropdownMenuItem } from '@octavian-tocan/react-dropdown';
import { ImageIcon } from 'lucide-react';
import type { ComponentProps } from 'react';
import { usePromptInputAttachments } from './prompt-input-context';

/** Props for the action that opens the prompt input file chooser. */
export type PromptInputActionAddAttachmentsProps = ComponentProps<typeof DropdownMenuItem> & {
  label?: string;
};

/** Menu item that opens the prompt input file chooser. */
export const PromptInputActionAddAttachments = ({
  label = 'Add photos or files',
  ...props
}: PromptInputActionAddAttachmentsProps) => {
  const attachments = usePromptInputAttachments();

  return (
    <DropdownMenuItem
      {...props}
      onSelect={(e) => {
        e.preventDefault();
        attachments.openFileDialog();
      }}
    >
      <ImageIcon className="mr-2 size-4" /> {label}
    </DropdownMenuItem>
  );
};
