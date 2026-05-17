'use client';

import { ChatPromptSuggestions } from '@octavian-tocan/react-chat-composer';
import type * as React from 'react';
import { useEffect } from 'react';
import { useStickToBottomContext } from 'use-stick-to-bottom';
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input';
import { useWhimsyTile } from '@/features/whimsy';
import type { ChatMessage } from '@/lib/types';
import { Conversation, ConversationContent } from '../../components/ai-elements/conversation';
import { AssistantMessage } from './components/AssistantMessage';
import { ChatComposer } from './components/ChatComposer';
import { ConnectAppsStrip } from './components/ConnectAppsStrip';
import { UserMessage } from './components/UserMessage';
import type { ChatReasoningLevel } from './constants';
import type { ChatModelOption } from './hooks/use-chat-models';

/**
 * Discriminated state for the model-catalog request.
 *
 * Replaces independent `isCatalogLoading` + `isCatalogError` booleans so the
 * surfacing components ({@link LandingState}, {@link ConversationView}) stay
 * under React Doctor's "stacked boolean flags" warning threshold. The three
 * states are mutually exclusive: a catalog request can be in flight, can
 * have failed, or can have succeeded — never two at once.
 */
export type CatalogStatus = 'loading' | 'error' | 'ready';

/** Empty-state suggestion rows shown when no conversation has begun. */
const PROMPT_SUGGESTIONS = [
	{
		id: 'review-commits',
		label: 'Review my recent commits for correctness risks and maintainability concerns',
	},
	{ id: 'unblock-pr', label: 'Unblock my most recent open PR' },
	{ id: 'connect-apps', label: 'Connect my favorite apps to Pawrrtal' },
] as const;

/**
 * Props for the {@link ChatView} presentational component.
 */
type ChatProps = {
	/** Controlled text value of the composer's textarea. */
	composerText: string;
	/** Whether the assistant is generating a response (shows a loading indicator). */
	isLoading?: boolean;
	/** Callback fired when the composer's textarea content changes. */
	onChangeComposerText: (text: string) => void;
	/** Callback fired when the user submits a composer message. */
	onSendMessage: (message: PromptInputMessage) => void;
	/** The full conversation history to render. */
	chatHistory: Array<ChatMessage>;
	/** Live model catalog from `useChatModels()`, hoisted by the container. */
	models: readonly ChatModelOption[];
	/** Discriminated catalog fetch state — replaces independent loading/error flags. */
	catalogStatus: CatalogStatus;
	/** Selected canonical model ID (`host:vendor/model`) used for new chat requests. */
	selectedModelId: string;
	/** The selected reasoning level shown in the composer. */
	selectedReasoning: ChatReasoningLevel;
	/** Callback fired when the model selector changes. Emits the canonical wire form. */
	onSelectModel: (modelId: string) => void;
	/** Callback fired when the reasoning selector changes. */
	onSelectReasoning: (reasoning: ChatReasoningLevel) => void;
	/** Callback fired when an empty-state prompt suggestion is selected. */
	onSelectSuggestion: (prompt: string) => void;
	/** Index of the assistant message currently being regenerated, if any. */
	regeneratingIndex?: number | null;
	/** ID of the message whose copy button should currently render its "Copied!" state. */
	copiedMessageId?: string | null;
	/** Copy a message body to the clipboard with feedback. */
	onCopy?: (id: string, text: string) => void;
	/** Re-run the assistant turn at the given history index. */
	onRegenerate?: (assistantIndex: number) => void;
	/** Whether composer submission is blocked by onboarding readiness state. */
	isComposerBlocked?: boolean;
	/** Message shown inside composer when message submit is blocked. */
	composerBlockedMessage?: string;
	/** Open onboarding from composer when setup is blocked. */
	onOpenOnboarding?: () => void;
};

/**
 * Invisible anchor component that scrolls the conversation to the bottom
 * whenever `track` changes (i.e. when new messages are added).
 */
function ChatScrollAnchor({ track: _track }: { track: number }): React.JSX.Element | null {
	const { scrollToBottom } = useStickToBottomContext();
	useEffect(() => {
		scrollToBottom();
	}, [scrollToBottom]);
	return null;
}

/**
 * Whimsy texture overlay rendered behind the chat content. Returns `null`
 * when the user has disabled the texture in Settings → Appearance.
 *
 * Sits behind all chat content via tree order: an absolute sibling without
 * z-index paints after static children, so the content wrappers below need
 * `relative` to appear above it.
 */
function WhimsyOverlay(): React.JSX.Element | null {
	const whimsy = useWhimsyTile();
	if (!whimsy.cssUrl) return null;
	return (
		<>
			{whimsy.backgroundColor ? (
				<div
					aria-hidden="true"
					className="pointer-events-none absolute inset-0"
					style={{ backgroundColor: whimsy.backgroundColor }}
				/>
			) : null}
			<div
				aria-hidden="true"
				className="pointer-events-none absolute inset-0 text-foreground [mask-repeat:repeat] [-webkit-mask-repeat:repeat]"
				style={{
					backgroundColor: whimsy.tintColor,
					opacity: whimsy.opacity,
					maskImage: whimsy.cssUrl,
					WebkitMaskImage: whimsy.cssUrl,
					maskSize: whimsy.maskSize,
					WebkitMaskSize: whimsy.maskSize,
				}}
			/>
		</>
	);
}

/** Props shared between the empty-state and active-conversation composer rows. */
interface ComposerRowProps {
	composerText: string;
	isLoading?: boolean;
	/** Backend model catalog in the shape returned by `useChatModels()`. */
	models: readonly ChatModelOption[];
	/** Discriminated catalog fetch state — see {@link CatalogStatus}. */
	catalogStatus: CatalogStatus;
	/** Canonical model-ID wire form (`host:vendor/model`). */
	selectedModelId: string;
	selectedReasoning: ChatReasoningLevel;
	onChangeComposerText: (text: string) => void;
	onSendMessage: (message: PromptInputMessage) => void;
	/** Emits the canonical wire form. */
	onSelectModel: (modelId: string) => void;
	onSelectReasoning: (reasoning: ChatReasoningLevel) => void;
	isComposerBlocked?: boolean;
	composerBlockedMessage?: string;
	onOpenOnboarding?: () => void;
}

/**
 * Landing-state composer column rendered above the connect-apps strip and
 * suggestion list when the conversation is empty.
 */
function LandingState({
	composerText,
	isLoading,
	models,
	catalogStatus,
	selectedModelId,
	selectedReasoning,
	onChangeComposerText,
	onSelectModel,
	onSelectReasoning,
	onSelectSuggestion,
	onSendMessage,
	isComposerBlocked,
	composerBlockedMessage,
	onOpenOnboarding,
}: ComposerRowProps & {
	onSelectSuggestion: (prompt: string) => void;
}): React.JSX.Element {
	return (
		<div className="relative mx-auto flex size-full max-w-[60rem] min-w-0 flex-col">
			<div className="flex min-h-0 flex-1 flex-col items-center pt-[24vh]">
				<h1 className="mb-10 text-center text-[28px] font-medium tracking-normal text-balance text-foreground sm:text-[30px]">
					What should we build in Pawrrtal?
				</h1>
				<div className="relative flex w-full max-w-[48.75rem] flex-col">
					<ChatComposer
						className="relative z-10"
						isLoading={isLoading}
						catalogStatus={catalogStatus}
						models={[...models]}
						message={{
							content: composerText,
							files: [],
						}}
						onUpdateMessage={(event) => onChangeComposerText(event.target.value)}
						onSelectModel={onSelectModel}
						onSelectReasoning={(level) =>
							onSelectReasoning(level as ChatReasoningLevel)
						}
						onSendMessage={onSendMessage}
						isSubmitBlocked={isComposerBlocked}
						blockedMessage={composerBlockedMessage}
						onOpenOnboarding={onOpenOnboarding}
						onReplaceMessageContent={onChangeComposerText}
						selectedModelId={selectedModelId}
						selectedReasoning={selectedReasoning}
					/>
					<ConnectAppsStrip />
				</div>
				<ChatPromptSuggestions
					className="mt-5 w-full max-w-[48.75rem]"
					onSelectSuggestion={onSelectSuggestion}
					suggestions={[...PROMPT_SUGGESTIONS]}
				/>
			</div>
		</div>
	);
}

/** Renders one row of the conversation history. */
function ConversationRow({
	chatMessage,
	index,
	isLast,
	isLoading,
	regeneratingIndex,
	copiedMessageId,
	onCopy,
	onRegenerate,
}: {
	chatMessage: ChatMessage;
	index: number;
	isLast: boolean;
	isLoading?: boolean;
	regeneratingIndex?: number | null;
	copiedMessageId?: string | null;
	onCopy?: (id: string, text: string) => void;
	onRegenerate?: (assistantIndex: number) => void;
}): React.JSX.Element {
	if (chatMessage.role === 'assistant') {
		const messageId = `assistant-${index}`;
		const isCurrentlyRegenerating = regeneratingIndex === index;
		return (
			<AssistantMessage
				content={chatMessage.content}
				onCopy={onCopy ? () => onCopy(messageId, chatMessage.content) : undefined}
				onRegenerate={onRegenerate ? () => onRegenerate(index) : undefined}
				status={{
					isCopied: copiedMessageId === messageId,
					isFailed: chatMessage.assistant_status === 'failed',
					isRegenerating: isCurrentlyRegenerating,
					isStreaming: Boolean(isLoading && isLast),
				}}
				thinking={chatMessage.thinking}
				thinkingDurationSeconds={chatMessage.thinking_duration_seconds}
				timeline={chatMessage.timeline}
				toolCalls={chatMessage.tool_calls}
			/>
		);
	}
	const userMessageId = `user-${index}`;
	return (
		<UserMessage
			content={chatMessage.content}
			isCopied={copiedMessageId === userMessageId}
			onCopy={onCopy ? () => onCopy(userMessageId, chatMessage.content) : undefined}
		/>
	);
}

/**
 * Active-conversation surface — scrollable history above a follow-up composer.
 *
 * IMPORTANT: the scroll container is intentionally NOT wrapped in a
 * `max-w-[60rem]` column. Constraining the scroll area there meant the user
 * could only scroll while the cursor was over the narrow centered region.
 */
function ActiveConversationState({
	chatHistory,
	composerText,
	isLoading,
	models,
	catalogStatus,
	selectedModelId,
	selectedReasoning,
	onChangeComposerText,
	onSelectModel,
	onSelectReasoning,
	onSendMessage,
	regeneratingIndex,
	copiedMessageId,
	onCopy,
	onRegenerate,
	isComposerBlocked,
	composerBlockedMessage,
	onOpenOnboarding,
}: ComposerRowProps & {
	chatHistory: Array<ChatMessage>;
	regeneratingIndex?: number | null;
	copiedMessageId?: string | null;
	onCopy?: (id: string, text: string) => void;
	onRegenerate?: (assistantIndex: number) => void;
}): React.JSX.Element {
	return (
		<div className="relative flex size-full min-w-0 flex-col">
			<Conversation className="scrollbar-hide min-h-0 flex-1 overflow-y-auto" resize="smooth">
				<ConversationContent className="scrollbar-hide mx-auto w-full max-w-[48.75rem] px-0 pt-12 pb-6">
					{chatHistory.map((chatMessage, index) => {
						const messageKey = [
							chatMessage.role,
							chatMessage.thinking_started_at ?? 'saved',
							chatMessage.content.slice(0, 80),
						].join(':');
						return (
							<ConversationRow
								chatMessage={chatMessage}
								copiedMessageId={copiedMessageId}
								index={index}
								isLast={index === chatHistory.length - 1}
								isLoading={isLoading}
								key={messageKey}
								onCopy={onCopy}
								onRegenerate={onRegenerate}
								regeneratingIndex={regeneratingIndex}
							/>
						);
					})}
				</ConversationContent>
				<ChatScrollAnchor track={chatHistory.length} />
			</Conversation>
			<div className="mx-auto flex w-full max-w-[60rem] shrink-0 justify-center pb-4">
				<ChatComposer
					className="w-full max-w-[48.75rem]"
					isLoading={isLoading}
					catalogStatus={catalogStatus}
					models={[...models]}
					message={{
						content: composerText,
						files: [],
					}}
					onUpdateMessage={(event) => onChangeComposerText(event.target.value)}
					onSelectModel={onSelectModel}
					onSelectReasoning={(level) => onSelectReasoning(level as ChatReasoningLevel)}
					onSendMessage={onSendMessage}
					onReplaceMessageContent={onChangeComposerText}
					isSubmitBlocked={isComposerBlocked}
					blockedMessage={composerBlockedMessage}
					onOpenOnboarding={onOpenOnboarding}
					placeholderOverride="Ask a follow up"
					selectedReasoning={selectedReasoning}
					selectedModelId={selectedModelId}
				/>
			</div>
		</div>
	);
}

/**
 * Presentational chat component.
 *
 * Renders the conversation history, a loading indicator while the assistant
 * is thinking, and the message composer. All state management is handled by
 * the parent {@link ChatContainer}.
 *
 * The outer panel uses `rounded-surface-lg` (`--radius-surface-lg` in
 * `globals.css`, DESIGN.md `rounded.lg`) so its corners match the composer
 * chrome. Avoid `rounded-xl` here: with `--radius: 0`, `rounded-xl` is only ~4px.
 */
function ChatView({
	composerText,
	isLoading,
	chatHistory,
	models,
	catalogStatus,
	selectedModelId,
	selectedReasoning,
	onSendMessage,
	onChangeComposerText,
	onSelectModel,
	onSelectReasoning,
	onSelectSuggestion,
	regeneratingIndex,
	copiedMessageId,
	onCopy,
	onRegenerate,
	isComposerBlocked,
	composerBlockedMessage,
	onOpenOnboarding,
}: ChatProps): React.JSX.Element {
	const rowProps = {
		composerText,
		isLoading,
		models,
		catalogStatus,
		selectedModelId,
		selectedReasoning,
		onChangeComposerText,
		onSendMessage,
		onSelectModel,
		onSelectReasoning,
		isComposerBlocked,
		composerBlockedMessage,
		onOpenOnboarding,
	};

	// Chat panel reads `--background-elevated` directly via inline style
	// because the Tailwind v4 build was not always picking up new `@theme`
	// tokens during hot-reload — the panel was rendering as a stale gray on
	// every preset until this was switched off the bg- utility. The CSS
	// variable resolves live so the AppearanceProvider can re-tint per theme.
	return (
		<div
			className="relative z-10 flex h-[calc(100svh-3rem)] min-h-0 w-full overflow-hidden rounded-surface-lg px-4 shadow-panel-floating"
			style={{ backgroundColor: 'var(--background-elevated)' }}
		>
			<WhimsyOverlay />
			{chatHistory.length === 0 ? (
				<LandingState {...rowProps} onSelectSuggestion={onSelectSuggestion} />
			) : (
				<ActiveConversationState
					{...rowProps}
					chatHistory={chatHistory}
					copiedMessageId={copiedMessageId}
					onCopy={onCopy}
					onRegenerate={onRegenerate}
					regeneratingIndex={regeneratingIndex}
				/>
			)}
		</div>
	);
}

export default ChatView;
