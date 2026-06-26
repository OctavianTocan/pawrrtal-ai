/**
 * Full-featured chat input: files, shortcuts, and controller context.
 *
 * @fileoverview AI Elements — `prompt-input`.
 */

'use client';

export {
  PromptInputAttachment,
  type PromptInputAttachmentProps,
  PromptInputAttachments,
  type PromptInputAttachmentsProps,
} from './prompt-input-attachments';
export {
  type AttachmentsContext,
  LocalAttachmentsContext,
  type PromptInputControllerProps,
  type PromptInputProviderProps,
  type TextInputContext,
  useOptionalPromptInputController,
  usePromptInputAttachments,
} from './prompt-input-context';
export { PromptInput, type PromptInputMessage, type PromptInputProps } from './prompt-input-form';
export {
  PromptInputButton,
  type PromptInputButtonProps,
  PromptInputFooter,
  type PromptInputFooterProps,
  PromptInputHoverCard,
  PromptInputHoverCardContent,
  type PromptInputHoverCardContentProps,
  type PromptInputHoverCardProps,
  PromptInputHoverCardTrigger,
  type PromptInputHoverCardTriggerProps,
  PromptInputSubmit,
  type PromptInputSubmitProps,
} from './prompt-input-layout';
export { PromptInputTextarea, type PromptInputTextareaProps } from './prompt-input-textarea';
