/**
 * Shared attachment context for prompt input components.
 *
 * @fileoverview Extracted from prompt-input-context.tsx so React Fast
 * Refresh can treat that file as a components-only module.
 */

import type { FileUIPart } from 'ai';
import type { RefObject } from 'react';
import { createContext } from 'react';

/** Attachment controller exposed to prompt input child components. */
export type AttachmentsContext = {
  files: (FileUIPart & { id: string })[];
  add: (files: File[] | FileList) => void;
  remove: (id: string) => void;
  clear: () => void;
  openFileDialog: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
};

/** Local (per-PromptInput) attachments context. */
export const LocalAttachmentsContext = createContext<AttachmentsContext | null>(null);
