import type { ChatModelOption } from '../hooks/use-chat-models';

interface ResolveSelectedModelIdArgs {
	userChoice: string | null;
	initialModelId: string | null | undefined;
	models: readonly ChatModelOption[];
	defaultEntry: ChatModelOption | null;
}

/**
 * Resolve the model ID to render and send for the next turn.
 *
 * Priority:
 * 1. The user's in-session choice, when still present in the live catalog.
 * 2. The conversation's stored model, when opening an existing conversation.
 * 3. The catalog's first entry for a fresh conversation.
 */
export function resolveSelectedModelId({
	userChoice,
	initialModelId,
	models,
	defaultEntry,
}: ResolveSelectedModelIdArgs): string {
	if (userChoice !== null && models.some((model): boolean => model.id === userChoice)) {
		return userChoice;
	}
	if (
		typeof initialModelId === 'string' &&
		models.some((model): boolean => model.id === initialModelId)
	) {
		return initialModelId;
	}
	return defaultEntry?.id ?? '';
}
