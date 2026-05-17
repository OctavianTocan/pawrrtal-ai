'use client';
import type * as React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input';
import { useChatActivity } from '@/features/nav-chats/context/chat-activity-context';
import { useOnboardingReadiness } from '@/features/onboarding/hooks/use-onboarding-readiness';
import {
	OPEN_ONBOARDING_FLOW_EVENT,
	OPEN_ONBOARDING_SERVER_STEP_EVENT,
} from '@/features/onboarding/v2/OnboardingFlow';
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
import { isCanonicalModelId } from './lib/is-canonical-model-id';

/** Runtime guard for persisted reasoning levels. */
function isChatReasoningLevel(value: unknown): value is ChatReasoningLevel {
	return (
		typeof value === 'string' && (CHAT_REASONING_LEVELS as readonly string[]).includes(value)
	);
}

/**
 * Placeholder used while the persisted model ID is hydrating from
 * `localStorage` and/or the catalog request is in flight.
 *
 * `usePersistedState` requires a literal default, but we don't know the
 * catalog default until `useChatModels` resolves. The empty string never
 * passes {@link isCanonicalModelId}, so {@link resolveSelectedModelId}
 * always replaces it with the live catalog default on the first render
 * the catalog is available.
 */
const PENDING_MODEL_ID = '';

/**
 * Resolve the model ID to render: prefer the persisted value if it is both
 * canonically shaped AND present in the live catalog; otherwise fall back
 * to the catalog's `is_default` entry.
 *
 * Stale legacy IDs (e.g. `'gpt-5.5'` left over from an older build) fail
 * the canonical regex up-front, so this function never has to know about
 * legacy slugs explicitly.
 */
function resolveSelectedModelId(
	persistedId: string,
	models: readonly ChatModelOption[],
	defaultEntry: ChatModelOption | null
): string {
	if (
		isCanonicalModelId(persistedId) &&
		models.some((model): boolean => model.id === persistedId)
	) {
		return persistedId;
	}
	return defaultEntry?.id ?? '';
}

/** Return shape for {@link useSelectedChatModel}. */
interface UseSelectedChatModelResult {
	/** Live model catalog from `GET /api/v1/models`. */
	models: readonly ChatModelOption[];
	/** Currently selected canonical model ID — empty string while the catalog loads. */
	selectedModelId: string;
	/** Selects a catalog model immediately and then persists it. */
	selectModel: (modelId: string) => void;
	/** True until the first catalog response lands. */
	isCatalogLoading: boolean;
	/** True when catalog fetch or validation failed. */
	isCatalogError: boolean;
	/** True when at least one valid catalog entry is available. */
	hasCatalog: boolean;
	/** True when the catalog includes a default model. */
	hasDefaultModel: boolean;
	/** Backend target used for this catalog request. */
	backendConfigFingerprint: string;
}

/** Return shape for {@link useSelectedReasoning}. */
interface UseSelectedReasoningResult {
	/** Currently selected reasoning level. */
	selectedReasoning: ChatReasoningLevel;
	/** Selects a reasoning level immediately and then persists it. */
	selectReasoning: (reasoning: ChatReasoningLevel) => void;
}

/**
 * Hoists the catalog fetch + persisted-selection resolution so
 * {@link ChatContainer} stays under the project's per-function line budget.
 *
 * Storage value: canonical model ID (`host:vendor/model`) or `''` while
 * we're waiting for the catalog to seed the default. The validator
 * rejects any string that doesn't match the canonical shape, so
 * legacy slugs left in `localStorage` (e.g. `'gpt-5.5'`) silently fall
 * back to the catalog default on first read.
 */
function useSelectedChatModel(): UseSelectedChatModelResult {
	const {
		models,
		default: defaultModel,
		isLoading: isCatalogLoading,
		isError: isCatalogError,
		hasCatalog,
		hasDefaultModel,
		backendConfigFingerprint,
	} = useChatModels();

	const [persistedModelId, setPersistedModelId] = usePersistedState<string>({
		storageKey: CHAT_STORAGE_KEYS.selectedModelId,
		defaultValue: PENDING_MODEL_ID,
		validate: isCanonicalModelId,
	});

	// Derive during render: `usePersistedState` is backed by
	// `useSyncExternalStore` so the next render sees the updated value
	// synchronously after `setPersistedModelId`. The old "immediate" copy
	// + useEffect sync was redundant (and tripped react-doctor's
	// `no-derived-state-effect` rule).
	const selectedModelId = useMemo(
		() => resolveSelectedModelId(persistedModelId, models, defaultModel),
		[persistedModelId, models, defaultModel]
	);

	const selectModel = useCallback(
		(modelId: string): void => {
			const modelExists = models.some((model): boolean => model.id === modelId);
			if (!modelExists) return;
			setPersistedModelId(modelId);
		},
		[models, setPersistedModelId]
	);

	return {
		models,
		selectedModelId,
		selectModel,
		isCatalogLoading,
		isCatalogError,
		hasCatalog,
		hasDefaultModel,
		backendConfigFingerprint,
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
	backendConfigFingerprint: string;
	hasBackendConfig: boolean;
	hasCatalog: boolean;
	hasDefaultModel: boolean;
	hasWorkspaceReady: boolean;
	isCatalogError: boolean;
	isCatalogLoading: boolean;
	isModelUnavailable: boolean;
	isOnboardingReadinessLoading: boolean;
}

function buildComposerBlockedMessage({
	backendConfigFingerprint,
	hasBackendConfig,
	hasCatalog,
	hasDefaultModel,
	hasWorkspaceReady,
	isCatalogError,
	isCatalogLoading,
	isModelUnavailable,
	isOnboardingReadinessLoading,
}: ComposerBlockReason): string | undefined {
	if (isOnboardingReadinessLoading) return 'Checking workspace setup before sending.';
	if (!hasBackendConfig) return 'Connect a backend server to send messages.';
	if (!hasWorkspaceReady) return 'Finish workspace onboarding before sending messages.';
	if (isCatalogLoading) return 'Loading model catalog.';
	if (isCatalogError && process.env.NODE_ENV === 'production') {
		return 'Model catalog unavailable. Check backend connection.';
	}
	if (isCatalogError) {
		return `Model catalog unavailable from ${backendConfigFingerprint}. Check backend connection.`;
	}
	if (!hasCatalog) return 'No models are available from the connected backend.';
	if (!hasDefaultModel && isModelUnavailable) {
		return 'Model catalog has no default. Select a model before sending.';
	}
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
}

interface ComposerGateArgs {
	model: UseSelectedChatModelResult;
	hasBackendConfig: boolean;
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
	hasBackendConfig,
	hasWorkspaceReady,
	isOnboardingReadinessLoading,
}: ComposerGateArgs): ComposerGateResult {
	const isModelUnavailable = model.selectedModelId.length === 0;
	const isComposerBlocked =
		isOnboardingReadinessLoading ||
		!hasBackendConfig ||
		!hasWorkspaceReady ||
		model.isCatalogLoading ||
		model.isCatalogError ||
		isModelUnavailable;
	const composerBlockedMessage = buildComposerBlockedMessage({
		backendConfigFingerprint: model.backendConfigFingerprint,
		hasBackendConfig,
		hasCatalog: model.hasCatalog,
		hasDefaultModel: model.hasDefaultModel,
		hasWorkspaceReady,
		isCatalogError: model.isCatalogError,
		isCatalogLoading: model.isCatalogLoading,
		isModelUnavailable,
		isOnboardingReadinessLoading,
	});
	const openSetup = useCallback(() => {
		const shouldOpenServerStep = !hasBackendConfig || model.isCatalogError;
		const event = shouldOpenServerStep
			? new Event(OPEN_ONBOARDING_SERVER_STEP_EVENT)
			: new Event(OPEN_ONBOARDING_FLOW_EVENT);
		window.dispatchEvent(event);
	}, [hasBackendConfig, model.isCatalogError]);
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
 * - Fetches the live model catalog (via {@link useChatModels}) and resolves
 *   the persisted selection against it.
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
}: ChatContainerProps): React.JSX.Element | null {
	const {
		hasBackendConfig,
		hasWorkspaceReady,
		isLoading: isOnboardingReadinessLoading,
	} = useOnboardingReadiness();
	const model = useSelectedChatModel();
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
		hasBackendConfig,
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
