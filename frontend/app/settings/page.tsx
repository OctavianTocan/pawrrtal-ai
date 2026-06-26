/**
 * Settings page route.
 *
 * @fileoverview Mounts {@link SettingsLayout} at `/settings` outside the
 * `(app)` route group so the chat sidebar chrome does not render.
 */

import type { Metadata } from 'next';
import { SettingsLayout } from '@/features/settings/SettingsLayout';

export const metadata: Metadata = {
  title: 'Settings — Pawrrtal',
};

export default function SettingsPage(): React.JSX.Element {
  return <SettingsLayout />;
}
