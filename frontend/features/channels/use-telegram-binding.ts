/**
 * Stateful hook driving the Telegram connect dialog + the Settings row.
 *
 * Encapsulates the three states the binding flow can be in (idle,
 * pending a redemption, connected) and the periodic poll that flips
 * the UI to "connected" once the bot finishes redeeming the code.
 *
 * Uses TanStack Query for the channel list so that connection state is
 * shared across all consumers (onboarding + settings) via the cache.
 * During the pending-code phase, `refetchInterval` polls every 2 s;
 * outside that window the query uses default stale-while-revalidate.
 *
 * @fileoverview React hook that wraps the channels API for the UI layer.
 */

'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react';
import { useAuthedQuery } from '@/hooks/use-authed-query';
import { API_ENDPOINTS } from '@/lib/api';
import {
	type ChannelBinding,
	ChannelNotConfiguredError,
	issueTelegramLinkCode,
	type TelegramLinkCode,
	unlinkTelegram,
} from '@/lib/channels';

const POLL_INTERVAL_MS = 2000;
const PROVIDER = 'telegram';
const CHANNELS_QUERY_KEY = ['channels'] as const;

interface UseTelegramBindingOptions {
	onConnected?: () => void;
}

/** Public shape returned by {@link useTelegramBinding}. */
export interface TelegramBindingState {
	/** Latest known binding row, or null when none. */
	binding: ChannelBinding | null;
	/** Active link code while the dialog is waiting on bot redemption. */
	pendingCode: TelegramLinkCode | null;
	/** Truthy while a network request is in flight. */
	isBusy: boolean;
	/** Last error message surfaced from the API, or null. */
	error: string | null;
	/** True iff the deployment intentionally has no bot configured. */
	notConfigured: boolean;
	/** Force a fresh `/api/v1/channels` fetch (e.g. on dialog open). */
	refresh: () => Promise<void>;
	/** Issue a new code and start polling for the bind to land. */
	startConnect: () => Promise<void>;
	/** Stop polling and forget the active code (e.g. dialog dismissed). */
	cancelConnect: () => void;
	/** Drop the binding server-side. */
	disconnect: () => Promise<void>;
}

/**
 * Hook that owns the Telegram binding state machine.
 *
 * Backed by TanStack Query so channel state is shared across all
 * consumers via the `['channels']` cache key. The onboarding step and
 * Settings Channels section both read from the same cache entry.
 */
export function useTelegramBinding(options: UseTelegramBindingOptions = {}): TelegramBindingState {
	const queryClient = useQueryClient();
	const [pendingCode, setPendingCode] = useState<TelegramLinkCode | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [notConfigured, setNotConfigured] = useState(false);
	const notifiedBindingKeyRef = useRef<string | null>(null);

	const fireConnected = useEffectEvent((): void => {
		options.onConnected?.();
	});

	const channelsQuery = useAuthedQuery<ChannelBinding[]>(
		CHANNELS_QUERY_KEY,
		API_ENDPOINTS.channels.list,
		{ refetchInterval: pendingCode ? POLL_INTERVAL_MS : undefined }
	);

	const binding = channelsQuery.data?.find((row) => row.provider === PROVIDER) ?? null;

	const bindingKey =
		binding && pendingCode
			? [binding.provider, binding.external_user_id, binding.external_chat_id ?? ''].join(':')
			: null;

	useEffect(() => {
		if (!bindingKey) return;
		if (notifiedBindingKeyRef.current === bindingKey) return;
		notifiedBindingKeyRef.current = bindingKey;
		setPendingCode(null);
		fireConnected();
	}, [bindingKey]);

	const linkMutation = useMutation({
		mutationFn: () => issueTelegramLinkCode(),
		onSuccess: (code) => {
			setPendingCode(code);
			setNotConfigured(false);
			setError(null);
		},
		onError: (cause) => {
			if (cause instanceof ChannelNotConfiguredError) {
				setNotConfigured(true);
				setError(cause.message);
			} else {
				setError(cause instanceof Error ? cause.message : 'Failed to start connection.');
			}
		},
	});

	const unlinkMutation = useMutation({
		mutationFn: () => unlinkTelegram(),
		onMutate: async () => {
			await queryClient.cancelQueries({ queryKey: CHANNELS_QUERY_KEY });
			const previous = queryClient.getQueryData<ChannelBinding[]>(CHANNELS_QUERY_KEY);
			queryClient.setQueryData<ChannelBinding[]>(
				CHANNELS_QUERY_KEY,
				(old) => old?.filter((row) => row.provider !== PROVIDER) ?? []
			);
			setPendingCode(null);
			return { previous };
		},
		onError: (_err, _vars, context) => {
			if (context?.previous) {
				queryClient.setQueryData(CHANNELS_QUERY_KEY, context.previous);
			}
			setError('Failed to disconnect.');
		},
		onSettled: () => {
			void queryClient.invalidateQueries({ queryKey: CHANNELS_QUERY_KEY });
		},
	});

	const isBusy = linkMutation.isPending || unlinkMutation.isPending;

	const refresh = useCallback(async (): Promise<void> => {
		await queryClient.invalidateQueries({ queryKey: CHANNELS_QUERY_KEY });
	}, [queryClient]);

	const startConnect = useCallback(async (): Promise<void> => {
		setError(null);
		notifiedBindingKeyRef.current = null;
		await linkMutation.mutateAsync();
	}, [linkMutation]);

	const cancelConnect = useCallback((): void => {
		setPendingCode(null);
		setError(null);
	}, []);

	const disconnect = useCallback(async (): Promise<void> => {
		setError(null);
		await unlinkMutation.mutateAsync();
	}, [unlinkMutation]);

	return {
		binding,
		pendingCode,
		isBusy,
		error,
		notConfigured,
		refresh,
		startConnect,
		cancelConnect,
		disconnect,
	};
}
