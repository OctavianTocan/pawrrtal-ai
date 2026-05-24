'use client';

import { Check, Loader2 } from 'lucide-react';
import type * as React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { TelegramConnectDialog } from '@/features/channels/TelegramConnectDialog';
import { listChannels } from '@/lib/channels';
import {
	MESSAGING_CHANNELS,
	type MessagingChannelId,
	type PersonalizationProfile,
} from '@/lib/personalization/storage';
import { cn } from '@/lib/utils';
import { OnboardingShell } from './onboarding-shell';

/** Props for {@link StepMessaging}. */
export interface StepMessagingProps {
	profile: PersonalizationProfile;
	onPatch: (patch: Partial<PersonalizationProfile>) => void;
	onFinish: () => void;
}

/**
 * Step 4 — connect at least one messaging channel.
 *
 * Non-Telegram rows remain visual toggles backed by `connectedChannels`.
 * Telegram mirrors `GET /api/v1/channels` once the snapshot loads (and
 * again after the bind dialog closes) so we stay in sync without mounting
 * a second {@link useTelegramBinding} instance alongside the dialog.
 */
export function StepMessaging({
	profile,
	onPatch,
	onFinish,
}: StepMessagingProps): React.JSX.Element {
	const connected = profile.connectedChannels ?? [];
	const [telegramDialogOpen, setTelegramDialogOpen] = useState(false);
	const [channelsReady, setChannelsReady] = useState(false);
	const [serverTelegramConnected, setServerTelegramConnected] = useState(false);

	const connectedRef = useRef(connected);
	connectedRef.current = connected;
	const onPatchRef = useRef(onPatch);
	onPatchRef.current = onPatch;

	const refreshTelegramSnapshot = useCallback(async (): Promise<void> => {
		let hasServerTelegramConnection = false;
		try {
			const rows = await listChannels();
			hasServerTelegramConnection = rows.some((row) => row.provider === 'telegram');
			setServerTelegramConnected(hasServerTelegramConnection);
		} catch {
			setServerTelegramConnected(false);
		} finally {
			setChannelsReady(true);
		}
		const current = connectedRef.current;
		if (hasServerTelegramConnection && !current.includes('telegram')) {
			onPatchRef.current({ connectedChannels: [...current, 'telegram'] });
		}
	}, []);

	useEffect(() => {
		if (telegramDialogOpen) return;
		void refreshTelegramSnapshot();
	}, [telegramDialogOpen, refreshTelegramSnapshot]);

	const hasOne = connected.length > 0 || serverTelegramConnected;

	const markChannelConnected = (id: MessagingChannelId): void => {
		if (connected.includes(id)) return;
		onPatch({ connectedChannels: [...connected, id] });
	};

	const toggleChannel = (id: MessagingChannelId): void => {
		if (id === 'telegram') {
			setTelegramDialogOpen(true);
			return;
		}
		const next = connected.includes(id)
			? connected.filter((entry) => entry !== id)
			: [...connected, id];
		onPatch({ connectedChannels: next });
	};

	const rowConnected = (id: MessagingChannelId): boolean => {
		if (id === 'telegram') {
			if (!channelsReady) return false;
			return serverTelegramConnected || connected.includes('telegram');
		}
		return connected.includes(id);
	};

	return (
		<OnboardingShell
			footer={
				<Button
					className="h-11 w-full max-w-sm cursor-pointer rounded-control bg-foreground px-8 text-sm font-semibold text-background shadow-none hover:bg-foreground/90 hover:shadow-minimal"
					disabled={!hasOne}
					onClick={onFinish}
					size="lg"
					type="button"
				>
					Finish messaging setup
				</Button>
			}
			subtitle="Connect at least one messaging channel to continue."
			title="Connect Messaging"
		>
			<div className="flex flex-col gap-2.5">
				{MESSAGING_CHANNELS.map((channel) => {
					const isConnected = rowConnected(channel.id);
					const showTelegramSpinner = channel.id === 'telegram' && !channelsReady;

					return (
						<div
							className="flex items-center justify-between gap-3 rounded-[12px] border border-foreground/10 bg-foreground/[0.02] px-4 py-3"
							key={channel.id}
						>
							<div className="flex items-center gap-3">
								<span
									aria-hidden="true"
									className="flex size-9 shrink-0 items-center justify-center rounded-[10px] text-white"
									style={{ backgroundColor: channel.color }}
								>
									{channel.label.charAt(0)}
								</span>
								<span className="text-sm font-medium text-foreground">
									Connect {channel.label}
								</span>
							</div>
							{showTelegramSpinner ? (
								<span className="flex h-9 min-w-24 items-center justify-center">
									<Loader2
										aria-label="Checking Telegram connection"
										className="size-4 animate-spin text-muted-foreground"
									/>
								</span>
							) : (
								<Button
									className={cn(
										'h-9 min-w-24 cursor-pointer px-4',
										isConnected &&
											'bg-success text-background hover:bg-success/85'
									)}
									onClick={() => toggleChannel(channel.id)}
									size="sm"
									type="button"
									variant={isConnected ? 'default' : 'default'}
								>
									{isConnected ? (
										<>
											<Check aria-hidden="true" className="mr-1 size-3.5" />
											Connected
										</>
									) : (
										'Connect'
									)}
								</Button>
							)}
						</div>
					);
				})}
			</div>
			<TelegramConnectDialog
				onConnected={() => markChannelConnected('telegram')}
				onOpenChange={setTelegramDialogOpen}
				open={telegramDialogOpen}
			/>
		</OnboardingShell>
	);
}
