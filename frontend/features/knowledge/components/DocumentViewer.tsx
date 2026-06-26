'use client';

/**
 * Document viewer rendered when the user opens a `.md` file from My Files.
 *
 * Two modes:
 *  - **Read mode** (default): the same prose renderer (Streamdown) the chat
 *    surface uses, with a toolbar offering "Edit", "Publish", and "Close".
 *  - **Edit mode**: a plain textarea constrained to the same max-width column
 *    as the prose view, with "Save" / "Cancel" buttons. On "Save" the
 *    component calls the `onSave` callback; if saving fails it shows an
 *    inline error banner below the toolbar.
 *
 * The component manages its own `editContent` draft state so the caller's
 * `markdown` prop stays the source-of-truth for the saved content and we
 * never mutate it directly.
 *
 * The toolbar action rows, body, and banners are split into module-level
 * subcomponents so the main `DocumentViewer` body fits inside Biome's
 * 120-lines-per-function gate.
 */

import { DropdownMenuItem, DropdownMenuSeparator, DropdownPanelMenu } from '@octavian-tocan/react-dropdown';
import {
  ChevronDownIcon,
  CopyIcon,
  DownloadIcon,
  Loader2Icon,
  PencilIcon,
  SaveIcon,
  SendIcon,
  UserPlusIcon,
  XIcon,
} from 'lucide-react';
import { type ReactNode, useCallback, useEffect, useReducer, useRef } from 'react';
import { Streamdown } from 'streamdown';

// ───────────────────────────────────────────────────────────────────────────
// Subcomponents
// ───────────────────────────────────────────────────────────────────────────

/** Edit-mode action bar: Cancel + Save. */
function EditActionsRow({
  canSave,
  isSaving,
  onCancel,
  onSave,
}: {
  canSave: boolean;
  isSaving: boolean;
  onCancel: () => void;
  onSave: () => void;
}): ReactNode {
  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={onCancel}
        disabled={isSaving}
        className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2.5 text-[12px] font-medium text-muted-foreground transition-colors duration-150 ease-out hover:bg-foreground-5 hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={onSave}
        disabled={isSaving || !canSave}
        className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md bg-foreground px-2.5 text-[12px] font-medium text-background transition-colors duration-150 ease-out hover:bg-foreground/90 disabled:pointer-events-none disabled:opacity-50"
      >
        {isSaving ? (
          <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin" />
        ) : (
          <SaveIcon aria-hidden="true" className="size-3.5" />
        )}
        {isSaving ? 'Saving...' : 'Save'}
      </button>
    </div>
  );
}

/** Read-mode action bar: optional Edit, Publish dropdown, Close. */
function ReadActionsRow({
  canEdit,
  onClose,
  onEdit,
}: {
  canEdit: boolean;
  onClose: () => void;
  onEdit: () => void;
}): ReactNode {
  return (
    <div className="flex items-center gap-1.5">
      {canEdit && (
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[12px] font-medium text-muted-foreground transition-colors duration-150 ease-out hover:bg-foreground-5 hover:text-foreground"
        >
          <PencilIcon aria-hidden="true" className="size-3.5" />
          Edit
        </button>
      )}

      <DropdownPanelMenu
        asChild
        usePortal
        align="end"
        contentClassName="popover-styled p-1 min-w-44"
        trigger={
          <button
            type="button"
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-full bg-foreground-5 pr-1.5 pl-3 text-[12px] font-medium text-foreground transition-colors duration-150 ease-out hover:bg-foreground-10"
          >
            <SendIcon aria-hidden="true" className="size-3.5" />
            Publish
            <ChevronDownIcon aria-hidden="true" className="size-3.5" />
          </button>
        }
      >
        <DropdownMenuItem>
          <CopyIcon className="size-3.5" />
          Copy
        </DropdownMenuItem>
        <DropdownMenuItem>
          <DownloadIcon className="size-3.5" />
          Download
        </DropdownMenuItem>
        <DropdownMenuItem>
          <DownloadIcon className="size-3.5" />
          Download as PDF
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <SendIcon className="size-3.5" />
          Publish
        </DropdownMenuItem>
        <DropdownMenuItem>
          <UserPlusIcon className="size-3.5" />
          Invite
        </DropdownMenuItem>
      </DropdownPanelMenu>

      <button
        type="button"
        onClick={onClose}
        aria-label="Close document"
        className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 hover:bg-foreground-5 hover:text-foreground"
      >
        <XIcon aria-hidden="true" className="size-4" />
      </button>
    </div>
  );
}

/** Save-failed inline banner. */
function SaveErrorBanner({ message }: { message: string }): ReactNode {
  return (
    <div className="mx-4 mb-2 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
      <span className="mt-0.5 shrink-0">⚠</span>
      <span>{message}</span>
    </div>
  );
}

/** "File changed externally" warning shown if the upstream markdown drifts mid-edit. */
function StaleWarningBanner({
  disabled,
  onDismiss,
  onReload,
}: {
  disabled: boolean;
  onDismiss: () => void;
  onReload: () => void;
}): ReactNode {
  return (
    <div className="mx-4 mb-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-300">
      <span className="shrink-0">⚠</span>
      <span className="flex-1">
        This file changed externally while you were editing. Saving now will overwrite the newer version.
      </span>
      <button
        type="button"
        onClick={onReload}
        disabled={disabled}
        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md border border-amber-500/40 bg-transparent px-2 text-[11px] font-medium text-amber-700 transition-colors duration-150 ease-out hover:bg-amber-500/10 disabled:pointer-events-none disabled:opacity-50 dark:text-amber-300"
      >
        Reload from server
      </button>
      <button
        type="button"
        onClick={onDismiss}
        disabled={disabled}
        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md bg-amber-600 px-2 text-[11px] font-medium text-white transition-colors duration-150 ease-out hover:bg-amber-700 disabled:pointer-events-none disabled:opacity-50"
      >
        Keep my draft
      </button>
    </div>
  );
}

/**
 * Body switch: edit-mode textarea OR read-mode prose renderer.
 *
 * Edit mode uses a plain `<textarea>` rather than a rich editor — Markdown
 * source editing is already familiar, keeps the bundle small, and avoids
 * the cursor-sync complexity of a preview-alongside-edit layout.
 *
 * Read mode uses the same Streamdown prose renderer the chat surface uses;
 * `min-h-0` lets the flex child shrink so the scroll container is the
 * inner div, not the page.
 */
function DocumentBody({
  editContent,
  isEditing,
  isSaving,
  markdown,
  onChangeContent,
}: {
  editContent: string;
  isEditing: boolean;
  isSaving: boolean;
  markdown: string;
  onChangeContent: (value: string) => void;
}): ReactNode {
  if (isEditing) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-10">
        <div className="mx-auto max-w-[680px]">
          <textarea
            aria-label="Document content editor"
            value={editContent}
            onChange={(e) => onChangeContent(e.target.value)}
            disabled={isSaving}
            spellCheck={false}
            className="w-full resize-none rounded-md border border-border bg-background px-4 py-3 font-mono text-[13px] leading-relaxed text-foreground focus:outline-none focus:ring-2 focus:ring-foreground/20 disabled:opacity-60"
            style={{ minHeight: '480px' }}
          />
        </div>
      </div>
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-10">
      <article className="prose prose-sm mx-auto max-w-[680px] text-foreground">
        <Streamdown>{markdown}</Streamdown>
      </article>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Main component
// ───────────────────────────────────────────────────────────────────────────

interface DocumentViewerProps {
  /** Filename label shown at the top-left of the viewer chrome. */
  filename: string;
  /** Markdown source rendered inside the body (read-mode) or pre-filled in
   *  the textarea (edit-mode entry). */
  markdown: string;
  /** Fired when the user clicks the close button. */
  onClose: () => void;
  /**
   * Called when the user clicks "Save" in edit mode with the new content.
   * The parent is responsible for the network call; while it's in-flight the
   * Save button shows a spinner and both Save and Cancel are disabled.
   * On error the parent should reject the promise so we can display a banner.
   */
  onSave?: (newContent: string) => Promise<void>;
}

interface DocumentViewerState {
  editContent: string;
  isEditing: boolean;
  isSaving: boolean;
  saveError: string | null;
  showStaleWarning: boolean;
}

type DocumentViewerAction =
  | { type: 'cancel-edit' }
  | { type: 'dismiss-stale-warning' }
  | { type: 'edit-content-changed'; content: string }
  | { type: 'enter-edit'; content: string }
  | { type: 'reload-content'; content: string }
  | { type: 'save-failed'; message: string }
  | { type: 'save-started' }
  | { type: 'save-succeeded' }
  | { type: 'save-stopped' }
  | { type: 'stale-warning-shown' };

const initialDocumentViewerState: DocumentViewerState = {
  editContent: '',
  isEditing: false,
  isSaving: false,
  saveError: null,
  showStaleWarning: false,
};

function documentViewerReducer(state: DocumentViewerState, action: DocumentViewerAction): DocumentViewerState {
  if (action.type === 'cancel-edit') {
    return { ...state, isEditing: false, saveError: null, showStaleWarning: false };
  }
  if (action.type === 'dismiss-stale-warning') {
    return { ...state, showStaleWarning: false };
  }
  if (action.type === 'edit-content-changed') {
    return { ...state, editContent: action.content };
  }
  if (action.type === 'enter-edit') {
    return {
      ...state,
      editContent: action.content,
      isEditing: true,
      saveError: null,
      showStaleWarning: false,
    };
  }
  if (action.type === 'reload-content') {
    return { ...state, editContent: action.content, showStaleWarning: false };
  }
  if (action.type === 'save-failed') {
    return { ...state, saveError: action.message };
  }
  if (action.type === 'save-started') {
    return { ...state, isSaving: true, saveError: null };
  }
  if (action.type === 'save-succeeded') {
    return { ...state, isEditing: false, showStaleWarning: false };
  }
  if (action.type === 'save-stopped') {
    return { ...state, isSaving: false };
  }
  if (action.type === 'stale-warning-shown') {
    return { ...state, showStaleWarning: true };
  }
  return state;
}

/**
 * Pure presentation. The container decides what Close does, and provides the
 * `onSave` handler that calls the write API.
 */
export function DocumentViewer({ filename, markdown, onClose, onSave }: DocumentViewerProps): ReactNode {
  const [state, dispatchViewer] = useReducer(documentViewerReducer, initialDocumentViewerState);
  const { editContent, isEditing, isSaving, saveError, showStaleWarning } = state;
  // Markdown the user *started* editing from. Set on Edit-button click so
  // we can detect when the file is overwritten externally (typically the
  // agent rewriting the same path) while a draft is in flight.
  const baselineMarkdownRef = useRef<string | null>(null);
  // Latest editContent mirrored into a ref so handleSave can read it
  // without listing it in its dep list (which would rebuild the callback
  // on every keystroke for no benefit — the only consumer is one button).
  const editContentRef = useRef('');

  useEffect(() => {
    editContentRef.current = editContent;
  }, [editContent]);

  // Watch for the upstream markdown drifting from the baseline mid-edit.
  // We do not auto-clobber the draft; the banner lets the user choose.
  useEffect(() => {
    if (!isEditing || baselineMarkdownRef.current === null) return;
    if (markdown !== baselineMarkdownRef.current) {
      dispatchViewer({ type: 'stale-warning-shown' });
    }
  }, [markdown, isEditing]);

  const handleEdit = useCallback(() => {
    baselineMarkdownRef.current = markdown;
    dispatchViewer({ type: 'enter-edit', content: markdown });
  }, [markdown]);

  const handleCancel = useCallback(() => {
    baselineMarkdownRef.current = null;
    dispatchViewer({ type: 'cancel-edit' });
  }, []);

  const handleReload = useCallback(() => {
    baselineMarkdownRef.current = markdown;
    dispatchViewer({ type: 'reload-content', content: markdown });
  }, [markdown]);

  const handleSave = useCallback(async () => {
    if (!onSave) return;
    dispatchViewer({ type: 'save-started' });
    try {
      await onSave(editContentRef.current);
      baselineMarkdownRef.current = null;
      dispatchViewer({ type: 'save-succeeded' });
    } catch (err) {
      dispatchViewer({
        type: 'save-failed',
        message: err instanceof Error ? err.message : 'Save failed — please try again.',
      });
    } finally {
      dispatchViewer({ type: 'save-stopped' });
    }
  }, [onSave]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center gap-2 px-4 py-2">
        <span className="flex-1 truncate text-[12px] text-muted-foreground">
          {filename}
          {isEditing && (
            <span className="ml-1.5 rounded bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
              editing
            </span>
          )}
        </span>
        {isEditing ? (
          <EditActionsRow canSave={Boolean(onSave)} isSaving={isSaving} onCancel={handleCancel} onSave={handleSave} />
        ) : (
          <ReadActionsRow canEdit={Boolean(onSave)} onClose={onClose} onEdit={handleEdit} />
        )}
      </header>
      {saveError && <SaveErrorBanner message={saveError} />}
      {showStaleWarning && (
        <StaleWarningBanner
          disabled={isSaving}
          onDismiss={() => dispatchViewer({ type: 'dismiss-stale-warning' })}
          onReload={handleReload}
        />
      )}
      <DocumentBody
        editContent={editContent}
        isEditing={isEditing}
        isSaving={isSaving}
        markdown={markdown}
        onChangeContent={(content) => dispatchViewer({ type: 'edit-content-changed', content })}
      />
    </div>
  );
}
