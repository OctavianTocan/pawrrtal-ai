'use client';

import { DropdownMenu } from '@octavian-tocan/react-dropdown';
import {
	ArrowUpIcon,
	ChevronDownIcon,
	HandIcon,
	ListChecksIcon,
	Loader2,
	PlusIcon,
	ShieldAlertIcon,
	ShieldCheckIcon,
	SlidersHorizontalIcon,
	SquareIcon,
} from 'lucide-react';
import type * as React from 'react';
import { usePromptInputAttachments } from '@/components/ai-elements/prompt-input';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { usePersistedState } from '@/hooks/use-persisted-state';
import { usePointerDownCommit } from '@/hooks/use-pointer-down-commit';
import { useTooltipDropdown } from '@/hooks/use-tooltip-dropdown';
import { cn } from '@/lib/utils';
import {
	CHAT_STORAGE_KEYS,
	DEFAULT_SAFETY_MODE,
	SAFETY_MODE_ADVANCED,
	SAFETY_MODE_ORDER,
	SAFETY_MODES,
	type SafetyMode,
} from '../constants';
import { WaveformTimeline } from './ChatComposerWaveform';
import { formatRecordingTime } from './chat-composer-speech';

/** Shared tooltip wrapper for compact composer controls. */
export function ComposerTooltip({
	children,
	content,
}: {
	children: React.ReactNode;
	content: string;
}): React.JSX.Element {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<span className="inline-flex">{children}</span>
			</TooltipTrigger>
			<TooltipContent side="top">{content}</TooltipContent>
		</Tooltip>
	);
}

/** Renders the file attachment trigger bound to the prompt input controller. */
export function AttachButton(): React.JSX.Element {
	const attachments = usePromptInputAttachments();

	return (
		<ComposerTooltip content="Attach files">
			<Button
				aria-label="Attach files"
				className="size-7 rounded-[7px] text-muted-foreground hover:text-foreground"
				onClick={attachments.openFileDialog}
				size="icon-xs"
				type="button"
				variant="ghost"
			>
				<PlusIcon aria-hidden="true" className="size-4" />
			</Button>
		</ComposerTooltip>
	);
}

/** Renders the compact plan-mode trigger used in the composer toolbar. */
export function PlanButton({
	isActive = false,
	onToggle,
}: {
	isActive?: boolean;
	onToggle?: () => void;
}): React.JSX.Element {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					className={cn(
						'h-7 gap-1 rounded-[7px] px-1.5 text-[12px] font-normal',
						isActive
							? 'bg-info/20 text-info hover:bg-info/25'
							: 'text-muted-foreground hover:text-foreground'
					)}
					onClick={onToggle}
					type="button"
					variant="ghost"
				>
					<ListChecksIcon aria-hidden="true" className="size-3.5" />
					Plan
				</Button>
			</TooltipTrigger>
			<TooltipContent side="top">
				<span className="block">Create a plan</span>
				<span className="block text-muted-foreground">Shift+Tab to show or hide</span>
			</TooltipContent>
		</Tooltip>
	);
}

interface SafetyModeMeta {
	/** Human-readable label shown in the dropdown and trigger. */
	label: string;
	/** Lucide icon used as the leading affordance for this mode. */
	Icon: typeof ShieldCheckIcon;
	/** Tailwind text color token applied to the trigger label + chevron. */
	colorClass: string;
	/** Optional icon-only tint on the composer trigger (inherits `colorClass` when omitted). */
	iconClass?: string;
	/** Tailwind background tint applied behind the icon for this mode. */
	bgClass: string;
}

/**
 * Static metadata for each safety mode. Indexed by {@link SafetyMode} so adding
 * a new mode forces a TypeScript error until both the union and metadata are updated.
 *
 * Each mode owns a distinct color (matching the Codex reference): blue =
 * Default, amber = Auto-review (cautious), red = Full access (dangerous),
 * neutral = Custom. Colors are picked from the project semantic tokens
 * (`--info`, `--warning`, `--destructive`) so dark/light themes stay
 * coherent without per-shade overrides.
 *
 * Lives next to the renderer (not in `constants.ts`) because the Lucide icon
 * components are React render concerns, not data; keeping them here means the
 * shared constants module stays free of UI imports.
 */
const SAFETY_MODE_META: Record<SafetyMode, SafetyModeMeta> = {
	'default-permissions': {
		label: 'Default permissions',
		Icon: HandIcon,
		colorClass: 'text-foreground/90',
		iconClass: 'text-info',
		bgClass: 'bg-info/15',
	},
	'auto-review': {
		label: 'Auto-review',
		Icon: ShieldCheckIcon,
		colorClass: 'text-warning',
		bgClass: 'bg-warning/15',
	},
	'full-access': {
		label: 'Full access',
		Icon: ShieldAlertIcon,
		colorClass: 'text-destructive',
		bgClass: 'bg-destructive/15',
	},
	custom: {
		label: 'Custom (config.toml)',
		Icon: SlidersHorizontalIcon,
		colorClass: 'text-muted-foreground',
		bgClass: 'bg-foreground/10',
	},
};

/** Runtime guard so older persisted strings don't crash the selector. */
function isSafetyMode(value: unknown): value is SafetyMode {
	return typeof value === 'string' && (SAFETY_MODES as readonly string[]).includes(value);
}

/** Renders the auto-review/safety permissions selector in the composer toolbar. */
export function AutoReviewSelector(): React.JSX.Element {
	const [safetyMode, setSafetyMode] = usePersistedState<SafetyMode>({
		storageKey: CHAT_STORAGE_KEYS.safetyMode,
		defaultValue: DEFAULT_SAFETY_MODE,
		validate: isSafetyMode,
	});
	// Same hook ModelSelectorPopover uses — keeps the tooltip suppressed during
	// the dropdown's closing window so a focus-return on the trigger doesn't
	// fire `Tooltip.onOpenChange(true)` with `data-state="instant-open"` while
	// the dropdown is still mid-fade.
	const { menuOpen, tooltipOpen, handleMenuOpenChange, handleTooltipOpenChange } =
		useTooltipDropdown();

	const activeMeta = SAFETY_MODE_META[safetyMode];
	const ActiveIcon = activeMeta.Icon;

	return (
		<TooltipProvider disableHoverableContent>
			<Tooltip onOpenChange={handleTooltipOpenChange} open={tooltipOpen}>
				<TooltipTrigger asChild>
					<span className="inline-flex">
						<DropdownMenu
							asChild
							align="start"
							closeOnSelect
							usePortal
							// Match ModelSelectorPopover's surface — `popover-styled` provides
							// the project's elevated background, layered shadow, and themed
							// border; `chat-composer-dropdown-menu` overrides the surface to
							// `--background-elevated` and the radius to `--radius-surface-lg`
							// so the dropdown reads as part of the chat shell.
							contentClassName="chat-composer-dropdown-menu popover-styled p-1 min-w-[208px]"
							getItemDisplay={(mode) => SAFETY_MODE_META[mode].label}
							getItemKey={(mode) => mode}
							// Marks advanced modes so a divider is rendered ABOVE the first
							// one (the package emits the separator before the marked item).
							getItemSeparator={(mode) => SAFETY_MODE_ADVANCED.has(mode)}
							items={SAFETY_MODE_ORDER}
							onOpenChange={handleMenuOpenChange}
							onSelect={setSafetyMode}
							placement="top"
							renderItem={(mode, _isSelected, onSelect) => (
								<SafetyModeMenuItem
									isSelected={mode === safetyMode}
									mode={mode}
									onSelect={onSelect}
								/>
							)}
							trigger={
								<Button
									className={cn(
										'h-7 gap-1 rounded-[7px] bg-transparent px-1.5 text-[12px] font-normal hover:bg-foreground/[0.04]',
										menuOpen && 'bg-foreground/[0.04]',
										activeMeta.colorClass
									)}
									type="button"
									variant="ghost"
								>
									<ActiveIcon
										aria-hidden="true"
										className={cn('size-3.5', activeMeta.iconClass)}
									/>
									{activeMeta.label}
									<ChevronDownIcon aria-hidden="true" className="size-3" />
								</Button>
							}
						/>
					</span>
				</TooltipTrigger>
				<TooltipContent side="top">Review code changes automatically</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

interface SafetyModeMenuItemProps {
	mode: SafetyMode;
	isSelected: boolean;
	onSelect: (mode: SafetyMode) => void;
}

/** Single dropdown row for a safety mode. Selected mode uses a filled dot instead of a checkmark. */
function SafetyModeMenuItem({
	mode,
	isSelected,
	onSelect,
}: SafetyModeMenuItemProps): React.JSX.Element {
	const { label, Icon, colorClass, bgClass } = SAFETY_MODE_META[mode];
	const commitSelection = usePointerDownCommit<HTMLButtonElement>(() => onSelect(mode));

	return (
		<button
			className={cn(
				'flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
				isSelected && 'bg-foreground/[0.06]'
			)}
			onClick={commitSelection.onClick}
			onPointerDown={commitSelection.onPointerDown}
			type="button"
		>
			<span className="flex items-center gap-2">
				<span
					aria-hidden="true"
					className={cn(
						'inline-flex size-5 items-center justify-center rounded-[5px]',
						bgClass,
						colorClass
					)}
				>
					<Icon className="size-3" />
				</span>
				<span className={isSelected ? 'font-medium' : undefined}>{label}</span>
			</span>
			{isSelected ? <span className="size-1.5 shrink-0 rounded-full bg-foreground" /> : null}
		</button>
	);
}

/** Renders live voice recording controls and the animated voice meter. */
export function VoiceMeter({
	elapsedSeconds,
	isTranscribing,
	meterLevel,
	onSend,
	onStop,
}: {
	elapsedSeconds: number;
	/** When true, swap the stop button for a loader and disable Send. */
	isTranscribing?: boolean;
	/** Live mic RMS (0–1) from {@link useVoiceTranscribe}; animates bar heights. */
	meterLevel: number;
	onSend: () => void;
	onStop: () => void;
}): React.JSX.Element {
	return (
		<div className="ml-2 flex min-w-0 flex-1 items-center gap-2">
			<WaveformTimeline isPaused={Boolean(isTranscribing)} meterLevel={meterLevel} />
			<span className="w-9 text-right text-[12px] text-muted-foreground tabular-nums">
				{formatRecordingTime(elapsedSeconds)}
			</span>
			<ComposerTooltip content={isTranscribing ? 'Transcribing...' : 'Stop and transcribe'}>
				<Button
					aria-label={isTranscribing ? 'Transcribing' : 'Stop and transcribe'}
					className="size-8 rounded-full bg-foreground-10 text-foreground hover:bg-foreground-15 disabled:cursor-not-allowed disabled:opacity-60"
					disabled={isTranscribing}
					onClick={onStop}
					size="icon-sm"
					type="button"
					variant="ghost"
				>
					{isTranscribing ? (
						<Loader2 aria-hidden="true" className="size-4 animate-spin" />
					) : (
						<SquareIcon aria-hidden="true" className="size-3 fill-current" />
					)}
				</Button>
			</ComposerTooltip>
			<ComposerTooltip
				content={isTranscribing ? 'Wait for transcription' : 'Transcribe and send'}
			>
				<Button
					aria-label="Transcribe and send"
					className="size-8 rounded-full bg-accent text-primary-foreground hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
					disabled={isTranscribing}
					onClick={onSend}
					size="icon-sm"
					type="button"
					variant="ghost"
				>
					<ArrowUpIcon aria-hidden="true" className="size-4" />
				</Button>
			</ComposerTooltip>
		</div>
	);
}
