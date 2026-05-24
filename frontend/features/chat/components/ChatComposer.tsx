'use client';

import { ArrowUpIcon, MicIcon, SquareIcon } from 'lucide-react';
import type * as React from 'react';
import { useEffect, useState } from 'react';
import {
	PromptInput,
	PromptInputAttachment,
	PromptInputAttachments,
	PromptInputFooter,
	type PromptInputMessage,
	PromptInputSubmit,
} from '@/components/ai-elements/prompt-input';
import { Button } from '@/components/ui/button';
import { usePersistedState } from '@/hooks/use-persisted-state';
import { cn } from '@/lib/utils';
import {
	CHAT_STORAGE_KEYS,
	type ChatReasoningLevel,
	DEFAULT_PLAN_MODE_VISIBLE,
} from '../constants';
import type { ChatModelOption } from '../hooks/use-chat-models';
import { useVoiceTranscribe } from '../hooks/use-voice-transcribe';
import {
	AttachButton,
	AutoReviewSelector,
	ComposerTooltip,
	PlanButton,
	VoiceMeter,
} from './ChatComposerControls';
import { ComposerTextareaRow, useComposerGhostCompletion } from './ComposerTextareaRow';
import { ConnectAppsStrip } from './ConnectAppsStrip';
import { buildTranscriptContent } from './chat-composer-speech';
import { ModelSelectorPopover } from './ModelSelectorPopover';

/**
 * Discriminated state for the model-catalog request.
 *
 * Mirrors {@link import('../ChatView').CatalogStatus}; redeclared here so
 * this component file has no dependency on the consumer module. Replaces
 * the older independent `isCatalogLoading` + `isCatalogError` booleans.
 */
export type CatalogStatus = 'loading' | 'error' | 'ready';

/** Props for the Codex-like chat composer island. */
export type ChatComposerProps = {
	/** The current message being composed by the user. */
	message: PromptInputMessage;
	/** Whether an assistant response is currently streaming. */
	isLoading?: boolean;
	/** Catalog entries from `useChatModels()` — passed down by the container. */
	models: readonly ChatModelOption[];
	/** Discriminated catalog fetch state — see {@link CatalogStatus}. */
	catalogStatus: CatalogStatus;
	/** Selected chat model ID in canonical wire form (`host:vendor/model`). */
	selectedModelId: string;
	/** Selected reasoning level. */
	selectedReasoning: ChatReasoningLevel;
	/** Additional classes for the root composer form. */
	className?: string;
	/**
	 * When true, renders the dismissible "Connect your apps" strip as an
	 * attached footer band at the bottom of the composer surface. Intended
	 * for the landing/empty-conversation state.
	 */
	showConnectAppsStrip?: boolean;
	/** Callback fired when the textarea content changes. */
	onUpdateMessage: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
	/** Callback fired when the user submits the message. */
	onSendMessage: (message: PromptInputMessage) => void;
	/** Callback fired when voice transcription should replace the draft content. */
	onReplaceMessageContent: (content: string) => void;
	/** Block submit when onboarding readiness is incomplete. */
	isSubmitBlocked?: boolean;
	/** Helper text shown below the composer while submit is blocked. */
	blockedMessage?: string;
	/** Open onboarding flow when user clicks the unblock CTA. */
	onOpenOnboarding?: () => void;
	/** Callback fired when the selected model changes. Emits the canonical wire form. */
	onSelectModel: (modelId: string) => void;
	/** Callback fired when the selected reasoning level changes. */
	onSelectReasoning: (reasoning: ChatReasoningLevel) => void;
	/** Callback fired when the connect-apps footer band is dismissed. */
	onDismissConnectApps?: () => void;
	/**
	 * Optional fixed placeholder. When set, overrides the rotating landing
	 * placeholder — used for the follow-up composer ("Ask a follow up") so
	 * an active conversation gets a stable label instead of cycling tips
	 * meant for an empty page.
	 */
	placeholderOverride?: string;
};

/** Module-level type guard so the validator reference stays stable across renders. */
function isBoolean(value: unknown): value is boolean {
	return typeof value === 'boolean';
}

/**
 * Persists the Plan-mode toggle across sessions. Defaults match
 * {@link DEFAULT_PLAN_MODE_VISIBLE} (off) so a fresh chat does not start in
 * Plan mode — the user opts in once and the choice sticks.
 */
function usePlanModeVisible(): readonly [
	boolean,
	(next: boolean | ((prev: boolean) => boolean)) => void,
] {
	return usePersistedState<boolean>({
		storageKey: CHAT_STORAGE_KEYS.planModeVisible,
		defaultValue: DEFAULT_PLAN_MODE_VISIBLE,
		validate: isBoolean,
	});
}

const EMPTY_COMPOSER_PLACEHOLDERS = [
	'Ask Pawrrtal anything. @ to mention context',
	'Press Cmd+B to toggle the sidebar',
	'Type @ to mention files, folders, or skills',
	'Attach files with +',
	'Use Auto-review to let Pawrrtal inspect changes',
] as const;
const DEFAULT_EMPTY_COMPOSER_PLACEHOLDER = 'Ask Pawrrtal anything. @ to mention context';
/** Milliseconds between rotating empty-composer placeholder tips. */
const PLACEHOLDER_ROTATION_INTERVAL_MS = 5200;

function useRotatingPlaceholder(hasContent: boolean): string {
	const [placeholderIndex, setPlaceholderIndex] = useState(0);

	// Reset inline during render when content appears, instead of via effect.
	if (hasContent && placeholderIndex !== 0) {
		setPlaceholderIndex(0);
	}

	useEffect(() => {
		if (hasContent) return;

		const intervalId = window.setInterval(() => {
			setPlaceholderIndex((index) => (index + 1) % EMPTY_COMPOSER_PLACEHOLDERS.length);
		}, PLACEHOLDER_ROTATION_INTERVAL_MS);

		return () => window.clearInterval(intervalId);
	}, [hasContent]);

	if (hasContent) {
		return DEFAULT_EMPTY_COMPOSER_PLACEHOLDER;
	}

	return EMPTY_COMPOSER_PLACEHOLDERS[placeholderIndex] ?? DEFAULT_EMPTY_COMPOSER_PLACEHOLDER;
}

/**
 * Props for the right-side toolbar cluster.
 *
 * Both `selectedModelId` and `selectedReasoning` are derived from
 * {@link ChatComposerProps} so the cluster can never drift away from the
 * model picker's literal-union typing.
 */
interface ComposerSendClusterProps {
	state: ComposerSendClusterState;
	models: ChatComposerProps['models'];
	catalogStatus: ChatComposerProps['catalogStatus'];
	selectedModelId: ChatComposerProps['selectedModelId'];
	selectedReasoning: ChatComposerProps['selectedReasoning'];
	onSelectModel: ChatComposerProps['onSelectModel'];
	onSelectReasoning: ChatComposerProps['onSelectReasoning'];
	onStartRecording: () => void;
}

interface ComposerSendClusterState {
	isRecording: boolean;
	isTranscribing: boolean;
	isLoading: ChatComposerProps['isLoading'];
	hasContent: boolean;
	isSubmitBlocked: boolean;
	/** When true, both Plan and Send buttons share a yellow accent. */
	isPlanMode: boolean;
}

/**
 * Right-side toolbar cluster (model picker + mic + submit) extracted out of
 * `ChatComposer` so the parent stays under the project's 120-line function
 * budget. Pure presentation — receives every input as a prop.
 */
function ComposerSendCluster({
	state,
	models,
	catalogStatus,
	selectedModelId,
	selectedReasoning,
	onSelectModel,
	onSelectReasoning,
	onStartRecording,
}: ComposerSendClusterProps): React.JSX.Element {
	const { hasContent, isLoading, isPlanMode, isRecording, isTranscribing, isSubmitBlocked } =
		state;
	const isDisabled = isSubmitBlocked || !hasContent || isLoading || isTranscribing;
	return (
		<div className={cn('ml-auto flex shrink-0 items-center gap-1', isRecording && 'hidden')}>
			<ModelSelectorPopover
				models={models}
				selectedModelId={selectedModelId}
				selectedReasoning={selectedReasoning}
				onSelectModel={onSelectModel}
				onSelectReasoning={onSelectReasoning}
				isError={catalogStatus === 'error'}
				isLoading={catalogStatus === 'loading'}
			/>
			<ComposerTooltip
				content={isTranscribing ? 'Transcribing...' : 'Click to dictate or hold ^M'}
			>
				<Button
					aria-label="Start voice input"
					aria-pressed={isRecording}
					className="size-8 rounded-full text-muted-foreground hover:bg-foreground/[0.08] hover:text-foreground"
					disabled={isTranscribing}
					onClick={onStartRecording}
					size="icon-sm"
					type="button"
					variant="ghost"
				>
					<MicIcon
						aria-hidden="true"
						className={cn('size-3.5', isTranscribing && 'animate-pulse')}
					/>
				</Button>
			</ComposerTooltip>
			<ComposerTooltip content={isTranscribing ? 'Wait for transcription' : 'Send message'}>
				<PromptInputSubmit
					className={cn(
						'size-8 cursor-pointer rounded-full',
						isPlanMode
							? 'bg-info text-background hover:bg-info/90 disabled:bg-foreground/20 disabled:text-background/60'
							: 'bg-accent text-primary-foreground hover:bg-accent/90 disabled:bg-foreground/20 disabled:text-background/60'
					)}
					disabled={isDisabled}
					status={isLoading ? 'streaming' : 'ready'}
				>
					{isLoading ? (
						<SquareIcon aria-hidden="true" className="size-2.5 fill-current" />
					) : (
						<ArrowUpIcon aria-hidden="true" className="size-3.5" />
					)}
				</PromptInputSubmit>
			</ComposerTooltip>
		</div>
	);
}

/**
 * Renders the main chat input island with inline controls and a model selector.
 */
export function ChatComposer({
	message,
	isLoading,
	models,
	catalogStatus,
	selectedModelId,
	selectedReasoning,
	className,
	showConnectAppsStrip,
	onUpdateMessage,
	onSendMessage,
	onReplaceMessageContent,
	isSubmitBlocked,
	blockedMessage,
	onOpenOnboarding,
	onSelectModel,
	onSelectReasoning,
	onDismissConnectApps,
	placeholderOverride,
}: ChatComposerProps): React.JSX.Element {
	const voice = useVoiceTranscribe();
	const isRecording = voice.status === 'recording' || voice.status === 'requesting-permission';
	const isTranscribing = voice.status === 'transcribing';
	const [recordingSeconds, setRecordingSeconds] = useState(0);
	/** When false, the Plan control is hidden (toggle with Shift+Tab from the composer). */
	const [isPlanTagVisible, setIsPlanTagVisible] = usePlanModeVisible();
	const isSubmitBlockedResolved = isSubmitBlocked ?? false;
	const hasContent = message.content.trim().length > 0;
	const rotatingPlaceholder = useRotatingPlaceholder(hasContent);
	// `placeholderOverride` (e.g. "Ask a follow up") wins over the rotating
	// landing tips so an active conversation gets a stable label.
	const placeholder = placeholderOverride ?? rotatingPlaceholder;

	useEffect(() => {
		if (!isRecording) {
			return;
		}

		const intervalId = window.setInterval(() => {
			setRecordingSeconds((seconds) => seconds + 1);
		}, 1000);

		return () => window.clearInterval(intervalId);
	}, [isRecording]);

	const startRecording = (): void => {
		setRecordingSeconds(0);
		void voice.startRecording();
	};

	const finishRecording = async ({ shouldSend }: { shouldSend: boolean }): Promise<void> => {
		const transcript = await voice.stopRecording();
		if (!transcript) {
			return;
		}

		const nextContent = buildTranscriptContent({
			currentContent: message.content,
			transcript,
		});

		if (shouldSend) {
			onSendMessage({ ...message, content: nextContent });
			return;
		}
		onReplaceMessageContent(nextContent);
	};

	const handleStopRecording = (): void => {
		void finishRecording({ shouldSend: false });
	};

	const handleSendRecording = (): void => {
		void finishRecording({ shouldSend: true });
	};

	const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLFormElement>): void => {
		if (event.key !== 'Tab' || !event.shiftKey) {
			return;
		}
		event.preventDefault();
		setIsPlanTagVisible((visible) => !visible);
	};

	const ghost = useComposerGhostCompletion({
		content: message.content,
		// Disabled during streaming + voice so the textarea isn't racing
		// another input source for the same draft.
		enabled: !isLoading && !isRecording && !isTranscribing && !isSubmitBlockedResolved,
		onReplaceMessageContent,
	});

	return (
		// Stacks the composer above the connect-apps strip via z-index so
		// the strip looks layered behind the chat box (see ConnectAppsStrip).
		<div className={cn('relative flex w-full max-w-[48.75rem] flex-col', className)}>
			<PromptInput
				className="relative z-10 w-full"
				// Composer surface = chat-panel surface (`--background-elevated`)
				// + hairline border, so it reads as a discrete control on the
				// panel without the old gray-cast `bg-foreground-5` wash.
				inputGroupClassName="chat-composer-input-group rounded-surface-lg border border-border/50 bg-[color:var(--background-elevated)] shadow-minimal"
				multiple={true}
				onKeyDown={handleComposerKeyDown}
				onSubmit={onSendMessage}
			>
				<PromptInputAttachments className="px-3 pt-2 pb-0">
					{(attachment) => <PromptInputAttachment data={attachment} />}
				</PromptInputAttachments>
				<ComposerTextareaRow
					ghost={ghost}
					hasContent={hasContent}
					onChange={onUpdateMessage}
					placeholder={placeholder}
					value={message.content}
				/>
				{/* `min-h-8` (32px) + `py-1` keeps the controls vertically
			    centered without giving the footer the extra 4px of slack
			    `min-h-9` was reading as. */}
				<PromptInputFooter className="min-h-8 px-1.5 py-1">
					<div className="flex min-w-0 flex-1 items-center gap-1">
						<AttachButton />
						{isRecording || isTranscribing ? (
							<VoiceMeter
								elapsedSeconds={recordingSeconds}
								isTranscribing={isTranscribing}
								meterLevel={voice.meterLevel}
								onSend={handleSendRecording}
								onStop={handleStopRecording}
							/>
						) : (
							<>
								{isPlanTagVisible ? (
									<PlanButton
										isActive={isPlanTagVisible}
										onToggle={() => setIsPlanTagVisible(false)}
									/>
								) : null}
								<AutoReviewSelector />
							</>
						)}
					</div>

					<ComposerSendCluster
						state={{
							hasContent,
							isLoading,
							isSubmitBlocked: isSubmitBlockedResolved,
							isPlanMode: isPlanTagVisible,
							isRecording,
							isTranscribing,
						}}
						models={models}
						catalogStatus={catalogStatus}
						selectedModelId={selectedModelId}
						selectedReasoning={selectedReasoning}
						onSelectModel={onSelectModel}
						onSelectReasoning={onSelectReasoning}
						onStartRecording={startRecording}
					/>
				</PromptInputFooter>
			</PromptInput>
			{isSubmitBlockedResolved && blockedMessage ? (
				<div className="mt-2 flex items-center justify-between gap-3 rounded-sm border border-info/30 bg-info/[0.08] px-2.5 py-1.5 text-[12px] text-foreground/85">
					<p className="leading-snug">{blockedMessage}</p>
					{onOpenOnboarding ? (
						<Button
							className="h-6 cursor-pointer rounded-full px-3 text-[12px] font-medium"
							onClick={onOpenOnboarding}
							size="sm"
							type="button"
							variant="outline"
						>
							Open setup
						</Button>
					) : null}
				</div>
			) : null}
			{showConnectAppsStrip ? <ConnectAppsStrip onDismiss={onDismissConnectApps} /> : null}
		</div>
	);
}
