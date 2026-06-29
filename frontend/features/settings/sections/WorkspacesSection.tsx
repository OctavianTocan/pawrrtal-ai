/**
 * @fileoverview Settings → Workspaces — per-workspace environment variable
 * overrides.
 *
 * Container that wires:
 *   - `useWorkspaceEnv()` — TanStack Query GET of the user's overrides.
 *   - `useUpsertWorkspaceEnv()` — TanStack mutation that PATCHes new
 *     values onto the encrypted .env file.
 *   - `WorkspacesSectionView` — pure presentation; receives the working
 *     copy + handlers as props.
 *
 * The container owns the working-copy state (form edits before Save) and
 * the per-key visibility toggle. The query/mutation handle abort-on-unmount,
 * caching, and dedup automatically.
 */

'use client';

import type * as React from 'react';
import { useRef, useState } from 'react';
import type { WorkspaceEnvKey } from '@/features/settings/workspace-env/use-workspace-env';
import {
  extractApiErrorMessage,
  useUpsertWorkspaceEnv,
  useWorkspaceEnv,
} from '@/features/settings/workspace-env/use-workspace-env';
import { WorkspacesSectionView } from '@/features/settings/workspace-env/WorkspacesSectionView';
import {
  emptyEnvRecord,
  workspaceEnvKeyMetasForResponse,
} from '@/features/settings/workspace-env/workspace-env-metadata';

/**
 * Settings → Workspaces container component.
 *
 * Manages local form state, kicks off the GET on mount via TanStack
 * Query, and submits edits via the upsert mutation. Renders nothing of
 * its own — delegates all presentation to {@link WorkspacesSectionView}.
 */
export function WorkspacesSection(): React.JSX.Element {
  const query = useWorkspaceEnv();
  const mutation = useUpsertWorkspaceEnv();
  const keyMetas = workspaceEnvKeyMetasForResponse(query.data);

  // Working copy: starts empty and is replaced once the query lands.
  // Edits are tracked locally so Discard can revert to the last
  // server-known state (`query.data`) without an extra fetch.
  const [values, setValues] = useState<Record<WorkspaceEnvKey, string>>(emptyEnvRecord);
  const [showTokens, setShowTokens] = useState<Partial<Record<WorkspaceEnvKey, boolean>>>({});
  const [isDirty, setIsDirty] = useState(false);
  // Track the last query data we synced so we can detect when the server
  // response changes and sync it inline during render instead of via effect.
  const lastSyncedDataRef = useRef(query.data);

  // Sync server data into the working copy when it arrives or refreshes,
  // but only while the form is clean. Without the `isDirty` guard, a
  // background refetch (e.g. on window focus) would clobber unsaved edits.
  if (query.data && query.data !== lastSyncedDataRef.current && !isDirty) {
    lastSyncedDataRef.current = query.data;
    setValues({ ...emptyEnvRecord(), ...query.data.vars });
  }

  const handleValueChange = (key: WorkspaceEnvKey, value: string): void => {
    setValues((current) => ({ ...current, [key]: value }));
    setIsDirty(true);
  };

  const handleToggleVisibility = (key: WorkspaceEnvKey): void => {
    setShowTokens((current) => ({ ...current, [key]: !current[key] }));
  };

  const handleSave = (): void => {
    mutation.mutate(values, {
      onSuccess: () => {
        setIsDirty(false);
      },
    });
  };

  const handleDiscard = (): void => {
    setValues({ ...emptyEnvRecord(), ...(query.data?.vars ?? {}) });
    setIsDirty(false);
    mutation.reset();
  };

  // Surface the most relevant error: mutation errors override query
  // errors because the user just attempted an action and expects
  // feedback on it. `extractApiErrorMessage` parses the FastAPI
  // `detail` body out of the fetch wrapper's "API Error: ..." string.
  let errorMessage: string | null = null;
  if (mutation.error !== null) {
    errorMessage = extractApiErrorMessage(mutation.error, 'Failed to save workspace environment.');
  } else if (query.error !== null) {
    errorMessage = extractApiErrorMessage(query.error, 'Failed to load workspace environment.');
  }

  return (
    <WorkspacesSectionView
      errorMessage={errorMessage}
      keyMetas={keyMetas}
      onDiscard={handleDiscard}
      onSave={handleSave}
      onToggleVisibility={handleToggleVisibility}
      onValueChange={handleValueChange}
      state={{
        isDirty,
        isLoading: query.isLoading,
        isSaving: mutation.isPending,
        showTokens,
      }}
      values={values}
    />
  );
}
