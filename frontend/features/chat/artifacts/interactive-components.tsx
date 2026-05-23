'use client';

/**
 * React renderers for the interactive components in the artifact catalog.
 *
 * @fileoverview Kept separate from {@link ./components} because these
 * renderers carry React state (selection, draft text, slider value) and
 * dispatch through {@link useArtifactInteraction}. Read-only renderers
 * stay stateless and visually small; the split also keeps each file under
 * the project's per-file line budget.
 *
 * Catalog ↔ renderer map:
 *  - ActionButton   → button click           → submits `label`
 *  - ChoiceGroup    → radio / checkbox group → submits selected labels (string or string[])
 *  - TextField      → text input / textarea  → submits the typed string
 *  - NumberField    → slider or numeric input → submits a number
 *
 * Each widget is intentionally minimal — feature creep here means the AI
 * has more knobs to misuse, not more capability for the user.
 */

import type { BaseComponentProps } from '@json-render/react';
import { type ReactNode, useId, useState } from 'react';
import type { ChatArtifactInteractionValue } from '@/lib/types';
import { useArtifactInteraction } from './interaction-context';

/** Default submit label when the AI doesn't supply one. */
const DEFAULT_SUBMIT_LABEL = 'Submit';

/** Default slider/input step when the AI omits one. */
const DEFAULT_NUMBER_STEP = 1;

/** Joiner used when a multi-choice picks multiple options. */
const MULTI_CHOICE_JOINER = ', ';

// Renderers receive `{ props, children }` from json-render. The runtime
// catalog (validated by zod before render) is the source of truth, so we
// type the loose surface as `BaseComponentProps<any>` (same pattern as
// `./components.tsx`) and narrow per-renderer with a local interface
// applied via a single cast. The renderer body stays strictly typed.
// biome-ignore lint/suspicious/noExplicitAny: see note above.
type LooseProps = BaseComponentProps<any>;

interface ActionButtonProps {
	label: string;
	actionId: string;
	style: 'primary' | 'secondary' | null;
}

/**
 * Single button. Renders even without a provider so previews stay visible,
 * but the disabled state mirrors the lack of a dispatcher so we never
 * silently swallow clicks.
 */
export function ActionButtonRenderer(raw: LooseProps): ReactNode {
	const props = raw.props as ActionButtonProps;
	const ctx = useArtifactInteraction();
	const disabled = ctx === null || !ctx.hasHandler;
	const className =
		props.style === 'secondary'
			? 'artifact-action-button artifact-action-button-secondary'
			: 'artifact-action-button artifact-action-button-primary';
	return (
		<button
			aria-disabled={disabled}
			className={className}
			disabled={disabled}
			onClick={() => {
				if (disabled) return;
				void ctx?.submit({
					actionId: props.actionId,
					label: props.label,
					value: props.label,
				});
			}}
			type="button"
		>
			{props.label}
		</button>
	);
}

interface ChoiceOption {
	value: string;
	label: string;
}

interface ChoiceGroupProps {
	actionId: string;
	prompt: string | null;
	multi: boolean;
	options: ChoiceOption[];
}

function buildChoiceSummary(options: ChoiceOption[], selected: string[]): string {
	const selectedSet = new Set(selected);
	const labels: string[] = [];
	for (const option of options) {
		if (selectedSet.has(option.value)) {
			labels.push(option.label);
		}
	}
	return labels.join(MULTI_CHOICE_JOINER);
}

/**
 * Radio (single) or checkbox (multi) group. Submits the selected labels
 * (joined for multi-select) as the follow-up user message; the structured
 * value carries the option keys so the AI can match them deterministically.
 */
export function ChoiceGroupRenderer(raw: LooseProps): ReactNode {
	const props = raw.props as ChoiceGroupProps;
	const ctx = useArtifactInteraction();
	const [selected, setSelected] = useState<readonly string[]>([]);
	const groupId = useId();

	const onToggle = (value: string): void => {
		setSelected((prev) => {
			if (props.multi) {
				return prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value];
			}
			return [value];
		});
	};

	const onSubmit = (): void => {
		if (selected.length === 0) return;
		const label = buildChoiceSummary(props.options, [...selected]);
		const payloadValue: ChatArtifactInteractionValue = props.multi
			? [...selected]
			: (selected[0] ?? '');
		void ctx?.submit({ actionId: props.actionId, label, value: payloadValue });
	};

	return (
		<div className="artifact-choice-group">
			{props.prompt ? <div className="artifact-choice-prompt">{props.prompt}</div> : null}
			<div className="artifact-choice-options">
				{props.options.map((option) => {
					const inputId = `${groupId}-${option.value}`;
					return (
						<label
							className="artifact-choice-option"
							htmlFor={inputId}
							key={option.value}
						>
							<input
								aria-label={option.label}
								checked={selected.includes(option.value)}
								id={inputId}
								name={groupId}
								onChange={() => onToggle(option.value)}
								type={props.multi ? 'checkbox' : 'radio'}
							/>
							<span>{option.label}</span>
						</label>
					);
				})}
			</div>
			<button
				className="artifact-action-button artifact-action-button-primary"
				disabled={ctx === null || !ctx.hasHandler || selected.length === 0}
				onClick={onSubmit}
				type="button"
			>
				{props.multi ? 'Submit selection' : 'Submit choice'}
			</button>
		</div>
	);
}

interface TextFieldProps {
	actionId: string;
	label: string;
	placeholder: string | null;
	multiline: boolean;
	submitLabel: string | null;
}

/**
 * Free-text input. Single-line submits on Enter; multi-line uses an
 * explicit Submit button to avoid trapping newline keystrokes.
 */
export function TextFieldRenderer(raw: LooseProps): ReactNode {
	const props = raw.props as TextFieldProps;
	const ctx = useArtifactInteraction();
	const [draft, setDraft] = useState('');
	const inputId = useId();

	const trimmed = draft.trim();
	const canSubmit = ctx !== null && trimmed.length > 0;

	const submit = (): void => {
		if (!canSubmit) return;
		void ctx?.submit({
			actionId: props.actionId,
			label: trimmed,
			value: trimmed,
		});
		setDraft('');
	};

	return (
		<div className="artifact-text-field">
			<label className="artifact-text-field-label" htmlFor={inputId}>
				{props.label}
			</label>
			{props.multiline ? (
				<textarea
					aria-label={props.label}
					className="artifact-text-field-control"
					id={inputId}
					onChange={(e) => setDraft(e.target.value)}
					placeholder={props.placeholder ?? undefined}
					rows={3}
					value={draft}
				/>
			) : (
				<input
					aria-label={props.label}
					className="artifact-text-field-control"
					id={inputId}
					onChange={(e) => setDraft(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === 'Enter' && canSubmit) {
							e.preventDefault();
							submit();
						}
					}}
					placeholder={props.placeholder ?? undefined}
					type="text"
					value={draft}
				/>
			)}
			<button
				className="artifact-action-button artifact-action-button-primary"
				disabled={!canSubmit}
				onClick={submit}
				type="button"
			>
				{props.submitLabel ?? DEFAULT_SUBMIT_LABEL}
			</button>
		</div>
	);
}

interface NumberFieldProps {
	actionId: string;
	label: string;
	min: number | null;
	max: number | null;
	step: number | null;
	defaultValue: number | null;
	kind: 'slider' | 'input';
	submitLabel: string | null;
}

function clampNumber(value: number, min: number | null, max: number | null): number {
	let next = value;
	if (min !== null && next < min) next = min;
	if (max !== null && next > max) next = max;
	return next;
}

/**
 * Numeric slider or input. The model picks the affordance (`kind`); we
 * submit a `number` and a `label` of the form `"<field-label>: <value>"`
 * so the chat history reads naturally.
 */
export function NumberFieldRenderer(raw: LooseProps): ReactNode {
	const props = raw.props as NumberFieldProps;
	const ctx = useArtifactInteraction();
	const inputId = useId();
	const initial = props.defaultValue ?? props.min ?? 0;
	const [value, setValue] = useState<number>(() => clampNumber(initial, props.min, props.max));
	const step = props.step ?? DEFAULT_NUMBER_STEP;

	const submit = (): void => {
		void ctx?.submit({
			actionId: props.actionId,
			label: `${props.label}: ${value}`,
			value,
		});
	};

	return (
		<div className="artifact-number-field">
			<label className="artifact-number-field-label" htmlFor={inputId}>
				{props.label}
				<span className="artifact-number-field-value">{value}</span>
			</label>
			<input
				aria-label={props.label}
				className={`artifact-number-field-control artifact-number-field-${props.kind}`}
				id={inputId}
				max={props.max ?? undefined}
				min={props.min ?? undefined}
				onChange={(e) =>
					setValue(clampNumber(Number(e.target.value), props.min, props.max))
				}
				step={step}
				type={props.kind === 'slider' ? 'range' : 'number'}
				value={value}
			/>
			<button
				className="artifact-action-button artifact-action-button-primary"
				disabled={ctx === null || !ctx.hasHandler}
				onClick={submit}
				type="button"
			>
				{props.submitLabel ?? DEFAULT_SUBMIT_LABEL}
			</button>
		</div>
	);
}
