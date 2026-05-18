/**
 * Prompt input textarea.
 *
 * @fileoverview Submits the parent form on Enter (without Shift), supports
 * pasting files, and removes the trailing attachment on Backspace when the
 * textarea is empty.
 */

'use client';

import {
	type ClipboardEventHandler,
	type JSX,
	type KeyboardEventHandler,
	type Ref,
	type TextareaHTMLAttributes,
	useRef,
} from 'react';
import { cn } from '../utils/cn';
import { usePromptInputAttachments } from './promptInputContext';

/** Props for the prompt input textarea. */
export interface PromptInputTextareaProps
	extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'name'> {
	/** Optional name override — defaults to `message` for the form payload. */
	name?: string;
	/** React 19 ref prop forwarded to the textarea. */
	ref?: Ref<HTMLTextAreaElement>;
}

/**
 * Auto-resizing textarea that drives the composer.
 *
 * Submits on `Enter` (without Shift), respects IME composition, pastes files
 * into the attachment list, and lets `Backspace` on an empty textarea remove
 * the most recent attachment.
 *
 * @returns A textarea wired into the prompt-input form.
 */
export function PromptInputTextarea({
	onChange,
	className,
	placeholder = 'What would you like to know?',
	name = 'message',
	ref,
	...props
}: PromptInputTextareaProps): JSX.Element {
		const attachments = usePromptInputAttachments();
		// IME composition state is only read inside the keydown handler,
		// never in JSX — useRef avoids spurious re-renders during
		// composition (react-doctor/rerender-state-only-in-handlers).
		const isComposingRef = useRef(false);

		const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
			if (e.key === 'Enter') {
				if (isComposingRef.current || e.nativeEvent.isComposing) return;
				if (e.shiftKey) return;
				e.preventDefault();
				const form = e.currentTarget.form;
				const submitButton = form?.querySelector(
					'button[type="submit"]',
				) as HTMLButtonElement | null;
				if (submitButton?.disabled) return;
				form?.requestSubmit();
			}

			if (e.key === 'Backspace' && e.currentTarget.value === '' && attachments.files.length > 0) {
				e.preventDefault();
				const lastAttachment = attachments.files.at(-1);
				if (lastAttachment) attachments.remove(lastAttachment.id);
			}
		};

		const handlePaste: ClipboardEventHandler<HTMLTextAreaElement> = (event) => {
			const items = event.clipboardData?.items;
			if (!items) return;
			const files: File[] = [];
			for (const item of items) {
				if (item.kind === 'file') {
					const file = item.getAsFile();
					if (file) files.push(file);
				}
			}
			if (files.length > 0) {
				event.preventDefault();
				attachments.add(files);
			}
		};

		return (
			<textarea
				ref={ref}
				className={cn(
					'field-sizing-content max-h-48 min-h-16 w-full resize-none bg-transparent outline-none placeholder:text-[var(--color-chat-muted)]',
					className,
				)}
				name={name}
				onChange={onChange}
				onCompositionEnd={() => {
					isComposingRef.current = false;
				}}
				onCompositionStart={() => {
					isComposingRef.current = true;
				}}
				onKeyDown={handleKeyDown}
				onPaste={handlePaste}
				placeholder={placeholder}
				{...props}
			/>
		);
}
