/**
 * Prompt input textarea behavior.
 *
 * @fileoverview Keyboard, paste, and controlled-provider behavior for prompt input textareas.
 */

'use client';

import {
	type ChangeEvent,
	type ClipboardEventHandler,
	type ComponentProps,
	type KeyboardEventHandler,
	useRef,
} from 'react';
import { InputGroupTextarea } from '@/components/ui/input-group';
import { useScrollEdges } from '@/hooks/use-scroll-edges';
import { cn } from '@/lib/utils';
import {
	useOptionalPromptInputController,
	usePromptInputAttachments,
} from './prompt-input-context';

/** Props for the prompt input textarea. */
export type PromptInputTextareaProps = ComponentProps<typeof InputGroupTextarea>;

/** Textarea that submits on Enter and supports pasted files. */
export const PromptInputTextarea = ({
	onChange,
	className,
	placeholder = 'What would you like to know?',
	...props
}: PromptInputTextareaProps) => {
	const controller = useOptionalPromptInputController();
	const attachments = usePromptInputAttachments();
	// IME composition state is only read inside the keydown handler, never
	// in the render output — use a ref so toggling it during composition
	// doesn't trigger spurious re-renders of the textarea.
	const isComposingRef = useRef(false);
	// Scroll-edge fade: when the textarea has more content above/below the
	// visible area, render top/bottom mask gradients via data-attributes
	// (CSS in globals.css → `[data-prompt-textarea]`).
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	const { canScrollUp, canScrollDown } = useScrollEdges(textareaRef);

	const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
		if (e.key === 'Enter') {
			if (isComposingRef.current || e.nativeEvent.isComposing) {
				return;
			}
			if (e.shiftKey) {
				return;
			}
			e.preventDefault();

			const form = e.currentTarget.form;
			const submitButton = form?.querySelector(
				'button[type="submit"]'
			) as HTMLButtonElement | null;
			if (submitButton?.disabled) {
				return;
			}

			form?.requestSubmit();
		}

		if (e.key === 'Backspace' && e.currentTarget.value === '' && attachments.files.length > 0) {
			e.preventDefault();
			const lastAttachment = attachments.files.at(-1);
			if (lastAttachment) {
				attachments.remove(lastAttachment.id);
			}
		}
	};

	const handlePaste: ClipboardEventHandler<HTMLTextAreaElement> = (event) => {
		const items = event.clipboardData?.items;

		if (!items) {
			return;
		}

		const files: File[] = [];

		for (const item of items) {
			if (item.kind === 'file') {
				const file = item.getAsFile();
				if (file) {
					files.push(file);
				}
			}
		}

		if (files.length > 0) {
			event.preventDefault();
			attachments.add(files);
		}
	};

	const controlledProps = controller
		? {
				value: controller.textInput.value,
				onChange: (e: ChangeEvent<HTMLTextAreaElement>) => {
					controller.textInput.setInput(e.currentTarget.value);
					onChange?.(e);
				},
			}
		: {
				onChange,
			};

	return (
		<InputGroupTextarea
			ref={textareaRef}
			className={cn('field-sizing-content max-h-48 min-h-16', className)}
			data-prompt-textarea=""
			data-scroll-up={canScrollUp ? 'true' : undefined}
			data-scroll-down={canScrollDown ? 'true' : undefined}
			name="message"
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
			{...controlledProps}
		/>
	);
};
