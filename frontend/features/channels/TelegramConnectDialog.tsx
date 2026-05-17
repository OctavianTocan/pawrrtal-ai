/**
 * Modal that walks a logged-in user through binding their Telegram
 * account to Pawrrtal.
 *
 * The dialog has three rendering modes that map to {@link useTelegramBinding}'s
 * state:
 *
 * - **idle** — first paint or after `cancelConnect()`. Shows the call
 *   to action; primary button issues a code.
 * - **pending** — code issued, waiting for the bot to redeem it.
 *   Shows the code, a 10-minute countdown, the `t.me/<bot>?start=...`
 *   deep-link button, and a copy-to-clipboard control.
 * - **connected** — `useTelegramBinding` polled `/api/v1/channels` and
 *   saw the binding land. The dialog flips to a confirmation screen so
 *   the user gets unambiguous feedback before closing.
 *
 * BEAN: status push via SSE instead of the 2s poll once the core
 * gateway exposes a channel-status stream.
 *
 * @fileoverview Onboarding + settings dialog for the Telegram bind flow.
 */

'use client';

import { Check, Copy, ExternalLink } from 'lucide-react';
import { useEffect, useEffectEvent, useMemo, useReducer } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from '@/lib/toast';
import { useTelegramBinding } from './use-telegram-binding';

type TelegramBindingState = ReturnType<typeof useTelegramBinding>;

interface TelegramConnectDialogBodyProps {
	countdownLabel: string | null;
	onCopy: () => void;
	state: TelegramBindingState;
}

function TelegramConnectDialogBody({
	countdownLabel,
	onCopy,
	state,
}: TelegramConnectDialogBodyProps): React.JSX.Element {
	if (state.notConfigured) {
		return <TelegramNotConfigured error={state.error} />;
	}

	if (state.binding !== null && state.pendingCode === null) {
		return <TelegramConnectedMessage displayHandle={state.binding.display_handle} />;
	}

	if (state.pendingCode !== null) {
		return (
			<TelegramPendingCode
				countdownLabel={countdownLabel}
				onCopy={onCopy}
				onRegenerate={() => void state.startConnect()}
				pendingCode={state.pendingCode}
			/>
		);
	}

	return (
		<TelegramIdleState
			error={state.error}
			isBusy={state.isBusy}
			onStart={() => void state.startConnect()}
		/>
	);
}

function TelegramNotConfigured({ error }: { error: string | null }): React.JSX.Element {
	return (
		<div className="space-y-3 text-sm text-muted-foreground">
			<p>{error ?? 'Telegram is not configured on this deployment.'}</p>
			<p>
				Set <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_BOT_USERNAME</code> in
				<code> backend/.env</code>, restart the backend, and try again.
			</p>
		</div>
	);
}

function TelegramConnectedMessage({
	displayHandle,
}: {
	displayHandle: string | null;
}): React.JSX.Element {
	return (
		<div className="space-y-4">
			<div className="flex items-center gap-2 text-sm font-medium text-success">
				<Check aria-hidden="true" className="size-4" /> Connected as
				{displayHandle ? (
					<span className="font-semibold">@{displayHandle}</span>
				) : (
					<span className="font-semibold">your Telegram account</span>
				)}
			</div>
			<p className="text-sm text-muted-foreground">
				You can now message the bot directly and Pawrrtal will respond from your account.
				Disconnect anytime from Settings → Channels.
			</p>
		</div>
	);
}

interface TelegramPendingCodeProps {
	countdownLabel: string | null;
	onCopy: () => void;
	onRegenerate: () => void;
	pendingCode: NonNullable<TelegramBindingState['pendingCode']>;
}

function TelegramPendingCode({
	countdownLabel,
	onCopy,
	onRegenerate,
	pendingCode,
}: TelegramPendingCodeProps): React.JSX.Element {
	return (
		<div className="space-y-4">
			<p className="text-sm text-muted-foreground">
				Open Telegram, send the code below to{' '}
				{pendingCode.bot_username ? (
					<a
						className="cursor-pointer font-medium text-foreground underline-offset-4 hover:underline"
						href={pendingCode.deep_link ?? `https://t.me/${pendingCode.bot_username}`}
						rel="noreferrer"
						target="_blank"
					>
						@{pendingCode.bot_username}
					</a>
				) : (
					<span className="font-medium text-foreground">the Pawrrtal bot</span>
				)}
				, and we'll connect this account.
			</p>
			<div className="flex items-center justify-between gap-2 rounded-xl border border-foreground/10 bg-foreground/[0.04] px-4 py-3">
				<code className="font-mono text-2xl font-semibold tracking-[0.25em]">
					{pendingCode.code}
				</code>
				<Button onClick={onCopy} size="sm" type="button" variant="outline">
					<Copy aria-hidden="true" className="mr-1 size-3.5" /> Copy
				</Button>
			</div>
			<div className="flex items-center justify-between text-xs text-muted-foreground">
				<span>
					Code expires in{' '}
					<span className="font-mono text-foreground">{countdownLabel ?? '...'}</span>
				</span>
				<button
					className="cursor-pointer underline-offset-4 hover:underline"
					onClick={onRegenerate}
					type="button"
				>
					Generate a new code
				</button>
			</div>
			{pendingCode.deep_link && (
				<Button asChild className="w-full" size="lg" type="button" variant="default">
					<a href={pendingCode.deep_link} rel="noreferrer" target="_blank">
						<ExternalLink aria-hidden="true" className="mr-2 size-4" />
						Open Telegram
					</a>
				</Button>
			)}
		</div>
	);
}

interface TelegramIdleStateProps {
	error: string | null;
	isBusy: boolean;
	onStart: () => void;
}

function TelegramIdleState({ error, isBusy, onStart }: TelegramIdleStateProps): React.JSX.Element {
	return (
		<div className="space-y-4 text-sm text-muted-foreground">
			<p>
				Get Pawrrtal in your pocket: connect your Telegram account and chat with your
				assistant from anywhere.
			</p>
			<Button className="w-full" disabled={isBusy} onClick={onStart} size="lg" type="button">
				{isBusy ? 'Generating code...' : 'Generate connection code'}
			</Button>
			{error && <p className="text-destructive">{error}</p>}
		</div>
	);
}

/** Props for {@link TelegramConnectDialog}. */
export interface TelegramConnectDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	/** Called when the binding has just been confirmed (lets onboarding step advance). */
	onConnected?: () => void;
}

export function TelegramConnectDialog({
	open,
	onOpenChange,
	onConnected,
}: TelegramConnectDialogProps): React.JSX.Element {
	const state = useTelegramBinding({ onConnected });
	const [secondsLeft, dispatchSecondsLeft] = useReducer(
		(_current: number | null, next: number | null): number | null => next,
		null
	);
	const pendingCode = state.pendingCode;
	const cancelConnect = useEffectEvent((): void => {
		state.cancelConnect();
	});

	// Track the live countdown for the pending code. `expires_at` arrives
	// as an ISO string so we recompute every second from the current time
	// — cheaper and more accurate than decrementing a stored counter.
	useEffect(() => {
		if (pendingCode === null) {
			dispatchSecondsLeft(null);
			return undefined;
		}
		// Backend emits naive UTC ISO strings (no `Z`/offset). Per the
		// ECMAScript spec, `new Date()` reads tz-less date-time forms as
		// LOCAL time, which puts `expires_at` in the past for any user
		// east of UTC and immediately fires `cancelConnect()` below.
		// Append `Z` only when no offset is already present so we keep
		// working if the backend ever switches to tz-aware timestamps.
		const rawExpiry = pendingCode.expires_at;
		const normalizedExpiry = /[zZ]|[+-]\d\d:?\d\d$/.test(rawExpiry)
			? rawExpiry
			: `${rawExpiry}Z`;
		const expiresAt = new Date(normalizedExpiry).getTime();
		const tick = (): void => {
			const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
			dispatchSecondsLeft(remaining);
			if (remaining === 0) {
				cancelConnect();
			}
		};
		tick();
		const id = setInterval(tick, 1000);
		return () => clearInterval(id);
	}, [pendingCode]);

	const countdownLabel = useMemo(() => {
		if (secondsLeft === null) {
			return null;
		}
		const minutes = Math.floor(secondsLeft / 60)
			.toString()
			.padStart(1, '0');
		const seconds = (secondsLeft % 60).toString().padStart(2, '0');
		return `${minutes}:${seconds}`;
	}, [secondsLeft]);

	const handleCopy = async (): Promise<void> => {
		if (!state.pendingCode) return;
		try {
			await navigator.clipboard.writeText(state.pendingCode.code);
			toast.success('Code copied');
		} catch {
			toast.error('Could not copy — long-press the code to select it.');
		}
	};

	return (
		<Dialog
			onOpenChange={(next) => {
				if (!next) {
					state.cancelConnect();
				}
				onOpenChange(next);
			}}
			open={open}
		>
			<DialogContent className="sm:max-w-md">
				<DialogHeader>
					<DialogTitle>Connect Telegram</DialogTitle>
				</DialogHeader>
				<TelegramConnectDialogBody
					countdownLabel={countdownLabel}
					onCopy={() => void handleCopy()}
					state={state}
				/>
			</DialogContent>
		</Dialog>
	);
}
