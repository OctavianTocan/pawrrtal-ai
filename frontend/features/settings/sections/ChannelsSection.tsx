/**
 * Settings → Channels — connect / disconnect third-party messaging surfaces.
 *
 * Today only the Telegram row is functional; Slack / WhatsApp /
 * iMessage are rendered as static "Coming soon" rows so the layout
 * matches the onboarding step and the user understands the roadmap.
 *
 * The Telegram row reuses the same `<TelegramConnectDialog />`
 * mounted in the onboarding flow, so the bind UX is bit-for-bit
 * identical regardless of where the user kicks it off from.
 *
 * @fileoverview Channels settings section.
 */

'use client';

import { Check, MessageSquare } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { TelegramConnectDialog } from '@/features/channels/TelegramConnectDialog';
import { useTelegramBinding } from '@/features/channels/use-telegram-binding';
import { MESSAGING_CHANNELS } from '@/lib/personalization/storage';

export function ChannelsSection(): React.JSX.Element {
  const telegram = useTelegramBinding();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto px-8 py-6">
      <header className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-foreground">Channels</h2>
        <p className="text-sm text-muted-foreground">
          Connect a messaging surface so you can reach Pawrrtal from anywhere. Each connection is bound to your account
          and only you can use it.
        </p>
      </header>

      <div className="flex flex-col gap-2.5">
        {MESSAGING_CHANNELS.map((channel) => {
          const isTelegram = channel.id === 'telegram';
          const isConnected = isTelegram && telegram.binding !== null;
          const handle = telegram.binding?.display_handle ?? null;

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
                  <MessageSquare className="size-4" />
                </span>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-foreground">{channel.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {isTelegram
                      ? isConnected
                        ? handle
                          ? `Connected as @${handle}`
                          : 'Connected'
                        : 'Chat with Pawrrtal from your Telegram account'
                      : 'Coming soon'}
                  </span>
                </div>
              </div>
              {isTelegram ? (
                isConnected ? (
                  <Button
                    disabled={telegram.isBusy}
                    onClick={() => void telegram.disconnect()}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button onClick={() => setDialogOpen(true)} size="sm" type="button">
                    Connect
                  </Button>
                )
              ) : (
                <Button disabled size="sm" type="button" variant="outline">
                  <Check aria-hidden="true" className="mr-1 size-3.5" />
                  Soon
                </Button>
              )}
            </div>
          );
        })}
      </div>

      <TelegramConnectDialog onOpenChange={setDialogOpen} open={dialogOpen} />
    </div>
  );
}
