/**
 * Shared attachment context for prompt input components.
 *
 * @fileoverview Extracted from prompt-input-context.tsx so React Fast
 * Refresh can treat that file as a components-only module.
 */

import { createContext } from 'react';
import type { AttachmentsContext } from './prompt-input-context';

/** Local (per-PromptInput) attachments context. */
export const LocalAttachmentsContext = createContext<AttachmentsContext | null>(null);
