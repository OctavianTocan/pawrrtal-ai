'use client';
import type * as React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input';
import { useChatActivity } from '@/features/nav-chats/context/chat-activity-context';
import { useOnboardingReadiness } from '@/features/onboarding/hooks/use-onboarding-readiness';
import { OPEN_ONBOARDING_FLOW_EVENT } from '@/features/onboarding/v2/OnboardingFlow';
import { usePersistedState } from '@/hooks/use-persisted-state';
import type { ChatArtifactInteractionPayload, ChatMessage } from '@/lib/types';
import { ArtifactInteractionProvider } from './artifacts/interaction-context';
import ChatView from './ChatView';
import {
	CHAT_REASONING_LEVELS,
	CHAT_STORAGE_KEYS,
	type ChatReasoningLevel,
	DEFAULT_REASONING_LEVEL,
} from './constants';
import { type ChatModelOption, useChatModels } from './hooks/use-chat-models';
import { useChatTurnController } from './hooks/use-chat-turn-controller';
import { resolveSelectedModelId } from './lib/model-selection';

/** Runtime guard for persisted reasoning levels. */
function isChatReasoningLevel(value: unknown): value is ChatReasoningLevel {
	return (
		typeof value === 'string' && (CHAT_REASONING_LEVELS as readonly string[]).includes(value)
	);
}

/** Return shape for {@link useSelectedChatModel}. */
interface UseSelectedChatModelResult {
	/** Live model catalog from `GET /api/v1/models`. */
	models: readonly ChatModelOption[];
	/** Currently selected canonical model ID — empty string while the catalog loads. */
	selectedModelId: string;
	/** Selects a catalog model for the rest of this session (in React state, not persisted). */
	selectModel: (modelId: string) => void;
	/** True until the first catalog response lands. */
	isCatalogLoading: boolean;
	/** True when catalog fetch or validation failed. */
	isCatalogError: boolean;
	/** True when at least one valid catalog entry is available. */
	hasCatalog: boolean;
}

/** Return shape for {@link useSelectedReasoning}. */
interface UseSelectedReasoningResult {
	/** Currently selected reasoning level. */
	selectedReasoning: ChatReasoningLevel;
	/** Selects a reasoning level immediately and then persists it. */
	selectReasoning: (reasoning: ChatReasoningLevel) => void;
}

/**
 * Hoists the catalog fetch + in-session selection so {@link ChatContainer}
 * stays under the project's per-function line budget.
 *
 * There is no `localStorage` persistence. Fresh sessions start on the
 * catalog's first model (`useChatModels().default`), while existing
 * conversations seed from the model stored on the conversation row.
 * The user's mid-session choice lives in React state (`userChoice`).
 */
function useSelectedChatModel(
	initialModelId: string | null | undefined
): UseSelectedChatModelResult {
	const {
		models,
		default: defaultModel,
		isLoading: isCatalogLoading,
		isError: isCatalogError,
		hasCatalog,
	} = useChatModels();

	// `null` means "no explicit choice yet" — derive the effective selection
	// from the catalog's first entry. Once the user picks a model it lives
	// here for the rest of the session (not persisted across reloads).
	const [userChoice, setUserChoice] = useState<string | null>(null);

	const selectedModelId = useMemo(
		() =>
			resolveSelectedModelId({
				userChoice,
				initialModelId,
				models,
				defaultEntry: defaultModel,
			}),
		[userChoice, initialModelId, models, defaultModel]
	);

	const selectModel = useCallback(
		(modelId: string): void => {
			const modelExists = models.some((model): boolean => model.id === modelId);
			if (!modelExists) return;
			setUserChoice(modelId);
		},
		[models]
	);

	return {
		models,
		selectedModelId,
		selectModel,
		isCatalogLoading,
		isCatalogError,
		hasCatalog,
	};
}

function useSelectedReasoning(): UseSelectedReasoningResult {
	const [persistedReasoning, setPersistedReasoning] = usePersistedState<ChatReasoningLevel>({
		storageKey: CHAT_STORAGE_KEYS.selectedReasoning,
		defaultValue: DEFAULT_REASONING_LEVEL,
		validate: isChatReasoningLevel,
	});

	const selectReasoning = useCallback(
		(reasoning: ChatReasoningLevel): void => {
			if (!isChatReasoningLevel(reasoning)) return;
			setPersistedReasoning(reasoning);
		},
		[setPersistedReasoning]
	);

	return {
		selectedReasoning: persistedReasoning,
		selectReasoning,
	};
}

/**
 * Publish chat-activity updates to the sidebar context and clear them on
 * unmount. Extracted from {@link ChatContainer} so the container stays
 * under the per-function line budget.
 */
function useChatActivitySync(
	conversationId: string,
	chatHistory: Array<ChatMessage>,
	isLoading: boolean
): void {
	const { publishActiveConversation, clearActiveConversation } = useChatActivity();

	// Keep the sidebar's chat-activity context in sync. Fires on every change so
	// the sidebar can show spinners, unread badges, and content-search matches.
	useEffect(() => {
		publishActiveConversation({ conversationId, chatHistory, isLoading });
	}, [chatHistory, conversationId, isLoading, publishActiveConversation]);

	// Clear activity state on unmount, guarded by conversationId so a stale
	// cleanup doesn't clobber a newly opened conversation.
	useEffect(
		() => () => clearActiveConversation(conversationId),
		[clearActiveConversation, conversationId]
	);
}

interface ComposerBlockReason {
	hasCatalog: boolean;
	hasWorkspaceReady: boolean;
	isCatalogError: boolean;
	isCatalogLoading: boolean;
	isModelUnavailable: boolean;
	isOnboardingReadinessError: boolean;
	isOnboardingReadinessLoading: boolean;
}

function buildComposerBlockedMessage({
	hasCatalog,
	hasWorkspaceReady,
	isCatalogError,
	isCatalogLoading,
	isModelUnavailable,
	isOnboardingReadinessError,
	isOnboardingReadinessLoading,
}: ComposerBlockReason): string | undefined {
	if (isOnboardingReadinessLoading) return 'Checking workspace setup before sending.';
	if (isOnboardingReadinessError) return 'Backend unavailable. Check the Pawrrtal service.';
	if (!hasWorkspaceReady) return 'Finish workspace onboarding before sending messages.';
	if (isCatalogLoading) return 'Loading model catalog.';
	if (isCatalogError) return 'Model catalog unavailable. Check the Pawrrtal service.';
	if (!hasCatalog) return 'No models are available from the connected backend.';
	if (isModelUnavailable) return 'Select a model before sending.';
	return undefined;
}

/**
 * Props for the {@link ChatContainer} component.
 */
interface ChatContainerProps {
	/** The conversation UUID. Always required so messages can be linked to a conversation. */
	conversationId: string;
	/** Pre-fetched messages to hydrate the chat on load (e.g. when opening an existing conversation). */
	initialChatHistory?: Array<ChatMessage>;
	/** Stored model id for an existing conversation. New conversations leave this unset. */
	initialModelId?: string | null;
}

interface ComposerGateArgs {
	model: UseSelectedChatModelResult;
	hasReadinessError: boolean;
	hasWorkspaceReady: boolean;
	isOnboardingReadinessLoading: boolean;
}

interface ComposerGateResult {
	composerBlockedMessage: string | undefined;
	isComposerBlocked: boolean;
	openSetup: () => void;
}

function useComposerGate({
	model,
	hasReadinessError,
	hasWorkspaceReady,
	isOnboardingReadinessLoading,
}: ComposerGateArgs): ComposerGateResult {
	const isModelUnavailable = model.selectedModelId.length === 0;
	const isComposerBlocked =
		isOnboardingReadinessLoading ||
		hasReadinessError ||
		!hasWorkspaceReady ||
		model.isCatalogLoading ||
		model.isCatalogError ||
		isModelUnavailable;
	const composerBlockedMessage = buildComposerBlockedMessage({
		hasCatalog: model.hasCatalog,
		hasWorkspaceReady,
		isCatalogError: model.isCatalogError,
		isCatalogLoading: model.isCatalogLoading,
		isModelUnavailable,
		isOnboardingReadinessError: hasReadinessError,
		isOnboardingReadinessLoading,
	});
	const openSetup = useCallback(() => {
		if (!hasWorkspaceReady) {
			window.dispatchEvent(new Event(OPEN_ONBOARDING_FLOW_EVENT));
		}
	}, [hasWorkspaceReady]);
	return { composerBlockedMessage, isComposerBlocked, openSetup };
}

/**
 * Stateful container that manages the chat lifecycle.
 *
 * Responsibilities:
 * - Creates a new conversation on first message (via {@link useCreateConversation}).
 * - Fires LLM title generation (via {@link useGenerateConversationTitle}).
 * - Streams assistant responses and accumulates chat history (via {@link useChatTurns}).
 * - Keeps the browser URL and the Next.js router in sync.
 * - Fetches the live model catalog (via {@link useChatModels}) and tracks the
 *   in-session model selection (seeded from the conversation row when present).
 *
 * Render logic is delegated to the presentational {@link ChatView}. The
 * composer's textarea value lives here as a plain controlled string —
 * `@octavian-tocan/react-chat-composer` accepts both controlled (`value` +
 * `onChange`) and uncontrolled modes; pawrrtal uses the controlled form so
 * the container can clear the draft on submit + insert prompt suggestions
 * programmatically.
 */
export default function ChatContainer({
	conversationId,
	initialChatHistory,
	initialModelId,
}: ChatContainerProps): React.JSX.Element | null {
	const {
		isError: hasReadinessError,
		hasWorkspaceReady,
		isLoading: isOnboardingReadinessLoading,
	} = useOnboardingReadiness();
	const model = useSelectedChatModel(initialModelId);
	const reasoning = useSelectedReasoning();
	const [composerText, setComposerText] = useState('');
	const chat = useChatTurnController({
		conversationId,
		initialChatHistory,
		selectedModelId: model.selectedModelId,
		selectedReasoning: reasoning.selectedReasoning,
	});
	const gate = useComposerGate({
		model,
		hasReadinessError,
		hasWorkspaceReady,
		isOnboardingReadinessLoading,
	});
	const handleSendMessage = useCallback(
		async (message: PromptInputMessage): Promise<void> => {
			if (gate.isComposerBlocked) {
				gate.openSetup();
				return;
			}
			setComposerText('');
			await chat.sendMessage(message);
		},
		[chat.sendMessage, gate]
	);
	const handleSelectSuggestion = useCallback((prompt: string) => {
		setComposerText(prompt);
	}, []);

	// Interactive-artifact dispatcher. v1 routes through the same
	// `sendMessage` flow as typed input — the widget's human-readable label
	// becomes the user message body, and the AI sees the interaction in
	// its next turn alongside the previously-rendered artifact (so it can
	// correlate which widget the user touched). When we add an in-place
	// mode later, swap this handler; the renderer never imports
	// `sendMessage` directly so widgets stay decoupled.
	const handleArtifactInteraction = useCallback(
		async (payload: ChatArtifactInteractionPayload): Promise<void> => {
			if (gate.isComposerBlocked) return;
			await chat.sendMessage({
				content: payload.label,
				files: [],
			});
		},
		[chat.sendMessage, gate.isComposerBlocked]
	);

	useChatActivitySync(conversationId, chat.chatHistory, chat.isLoading);

	return (
		<ArtifactInteractionProvider handler={handleArtifactInteraction}>
			<ChatView
				chatHistory={chat.chatHistory}
				composerText={composerText}
				copiedMessageId={chat.copiedId}
				catalogStatus={
					model.isCatalogLoading ? 'loading' : model.isCatalogError ? 'error' : 'ready'
				}
				isLoading={chat.isLoading}
				models={model.models}
				onChangeComposerText={setComposerText}
				onCopy={chat.copyMessage}
				onRegenerate={chat.regenerateMessage}
				onSelectModel={model.selectModel}
				onSelectReasoning={reasoning.selectReasoning}
				onSelectSuggestion={handleSelectSuggestion}
				isComposerBlocked={gate.isComposerBlocked}
				composerBlockedMessage={gate.composerBlockedMessage}
				onOpenOnboarding={gate.openSetup}
				onSendMessage={handleSendMessage}
				regeneratingIndex={chat.regeneratingIndex}
				selectedModelId={model.selectedModelId}
				selectedReasoning={reasoning.selectedReasoning}
			/>
		</ArtifactInteractionProvider>
	);
}
