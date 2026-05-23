/**
 * Prompt input context and provider state.
 *
 * @fileoverview Shared controller contexts for prompt input components.
 */

'use client';

import type { FileUIPart } from 'ai';
import { createContext, type PropsWithChildren, type RefObject, use } from 'react';
import { LocalAttachmentsContext } from './prompt-input-attachments-context';

/** Attachment controller exposed to prompt input child components. */
export type AttachmentsContext = {
	files: (FileUIPart & { id: string })[];
	add: (files: File[] | FileList) => void;
	remove: (id: string) => void;
	clear: () => void;
	openFileDialog: () => void;
	fileInputRef: RefObject<HTMLInputElement | null>;
};

/** Controlled textarea value used by provider-backed prompt inputs. */
export type TextInputContext = {
	value: string;
	setInput: (v: string) => void;
	clear: () => void;
};

/** Shared prompt input controller made available by `PromptInputProvider`. */
export type PromptInputControllerProps = {
	textInput: TextInputContext;
	attachments: AttachmentsContext;
	/** INTERNAL: Allows PromptInput to register its file input and opener callback. */
	__registerFileInput: (ref: RefObject<HTMLInputElement | null>, open: () => void) => void;
};

/** Props for the optional global prompt input provider. */
export type PromptInputProviderProps = PropsWithChildren<{
	initialInput?: string;
}>;

const PromptInputController = createContext<PromptInputControllerProps | null>(null);
const ProviderAttachmentsContext = createContext<AttachmentsContext | null>(null);

// Re-export from dedicated module so this file remains components-only for Fast Refresh.
export { LocalAttachmentsContext } from './prompt-input-attachments-context';

/** Read the provider-backed prompt input controller when one exists. */
export const useOptionalPromptInputController = () => use(PromptInputController);

/** Read provider-level attachments when the component is wrapped by a provider. */
const useOptionalProviderAttachments = () => use(ProviderAttachmentsContext);

/** Read the attachment controller for the current prompt input. */
export const usePromptInputAttachments = () => {
	const provider = useOptionalProviderAttachments();
	const local = use(LocalAttachmentsContext);
	const context = provider ?? local;
	if (!context) {
		throw new Error(
			'usePromptInputAttachments must be used within a PromptInput or PromptInputProvider'
		);
	}
	return context;
};
