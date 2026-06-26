'use client';

/**
 * Row primitives used by the Appearance settings section.
 *
 * Extracted out of `AppearanceSection.tsx` so the section file stays
 * under the project's 500-LOC budget. Each row owns its own debounce
 * + draft buffer so typing into the field doesn't lag the API; the
 * underlying pill picker is RAF-batched to avoid a re-render storm
 * during 60fps drags.
 */

import { type ChangeEvent, useCallback, useEffect, useReducer, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { ColorPill, SettingsRow } from '../primitives';
import { TEXT_INPUT_DEBOUNCE_MS, toHex } from './appearance-helpers';

const replaceDraft = (_current: string, next: string): string => next;

/** Props for the {@link ColorRow}. */
export interface ColorRowProps {
  /** Row label (e.g. "Background", "Accent"). */
  label: string;
  /** Fully-resolved CSS color string for this slot (handles oklch, named, etc.). */
  resolvedValue: string;
  /** User's typed override, or null/undefined when no override is set. */
  overrideValue: string | null | undefined;
  /** Default literal for this slot — also the placeholder for the value field. */
  defaultValue: string;
  /** Called with the new override (or null when the field is cleared). */
  onCommit: (next: string | null) => void;
}

/**
 * A single labeled color row — wraps the pill picker in a `SettingsRow`
 * and owns the local draft buffering so typing into the field doesn't
 * lag the API.
 *
 * Debounced commit fires `onCommit` once the user stops typing; native
 * picker commits via RAF-batched callback so a 60fps drag yields ≤60
 * PUTs/s instead of hundreds.
 */
export function ColorRow({
  label,
  resolvedValue,
  overrideValue,
  defaultValue,
  onCommit,
}: ColorRowProps): React.JSX.Element {
  const initialDraft = overrideValue ?? '';
  return (
    <ColorRowDraft
      defaultValue={defaultValue}
      initialDraft={initialDraft}
      key={initialDraft}
      label={label}
      onCommit={onCommit}
      resolvedValue={resolvedValue}
    />
  );
}

interface ColorRowDraftProps {
  defaultValue: string;
  initialDraft: string;
  label: string;
  onCommit: (next: string | null) => void;
  resolvedValue: string;
}

function ColorRowDraft({
  defaultValue,
  initialDraft,
  label,
  onCommit,
  resolvedValue,
}: ColorRowDraftProps): React.JSX.Element {
  const [draft, dispatchDraft] = useReducer(replaceDraft, initialDraft);
  const draftRef = useRef(draft);
  const commitRef = useRef(onCommit);

  // Keep refs current so the debounced timeout reads the latest values
  // without recreating the timer (per `react/state-safety` rule).
  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);
  useEffect(() => {
    commitRef.current = onCommit;
  }, [onCommit]);

  useEffect(() => {
    if (draft === initialDraft) return;
    const handle = setTimeout(() => {
      const next = draftRef.current.trim();
      commitRef.current(next.length === 0 ? null : next);
    }, TEXT_INPUT_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [draft, initialDraft]);

  const handleValueChange = useCallback((next: string) => dispatchDraft(next), []);

  // RAF-batched picker commit so 60fps dragging produces ≤60 PUTs/s.
  const pickerRafRef = useRef<number | null>(null);
  const handlePickerChange = useCallback((next: string) => {
    dispatchDraft(next);
    if (pickerRafRef.current !== null) cancelAnimationFrame(pickerRafRef.current);
    pickerRafRef.current = requestAnimationFrame(() => {
      pickerRafRef.current = null;
      commitRef.current(next);
    });
  }, []);

  useEffect(() => {
    const rafRef = pickerRafRef;
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const pickerSeed = toHex(initialDraft || resolvedValue);

  return (
    <SettingsRow label={label}>
      <ColorPill
        ariaLabel={`${label} color`}
        displayValue={draft}
        onPickerChange={handlePickerChange}
        onValueChange={handleValueChange}
        pickerSeed={pickerSeed}
        placeholder={defaultValue}
        resolvedColor={resolvedValue}
      />
    </SettingsRow>
  );
}

/** Props for the {@link FontRow}. */
export interface FontRowProps {
  /** Row label (e.g. "Display font"). */
  label: string;
  /** User's typed override, or null/undefined when no override is set. */
  overrideValue: string | null | undefined;
  /** Default literal for this slot — also the placeholder for the value field. */
  defaultValue: string;
  /** Called with the new override (or null when the field is cleared). */
  onCommit: (next: string | null) => void;
}

/**
 * Single font-family input row with the same debounce + placeholder
 * behavior as {@link ColorRow}.
 *
 * The font field stays a plain text input rather than a pill — the
 * value is a CSS font-family stack, not a single token, so a wider
 * field with monospace-friendly tabular-nums alignment beats a pill.
 */
export function FontRow({ label, overrideValue, defaultValue, onCommit }: FontRowProps): React.JSX.Element {
  const initialDraft = overrideValue ?? '';
  return (
    <FontRowDraft
      defaultValue={defaultValue}
      initialDraft={initialDraft}
      key={initialDraft}
      label={label}
      onCommit={onCommit}
    />
  );
}

interface FontRowDraftProps {
  defaultValue: string;
  initialDraft: string;
  label: string;
  onCommit: (next: string | null) => void;
}

function FontRowDraft({ defaultValue, initialDraft, label, onCommit }: FontRowDraftProps): React.JSX.Element {
  const [draft, dispatchDraft] = useReducer(replaceDraft, initialDraft);
  const draftRef = useRef(draft);
  const commitRef = useRef(onCommit);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);
  useEffect(() => {
    commitRef.current = onCommit;
  }, [onCommit]);

  useEffect(() => {
    if (draft === initialDraft) return;
    const handle = setTimeout(() => {
      const next = draftRef.current.trim();
      commitRef.current(next.length === 0 ? null : next);
    }, TEXT_INPUT_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [draft, initialDraft]);

  const updateFontFamilyDraft = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    dispatchDraft(event.target.value);
  }, []);

  return (
    <SettingsRow label={label}>
      <Input
        aria-label={`${label} family`}
        className="w-72 text-xs"
        onChange={updateFontFamilyDraft}
        placeholder={defaultValue}
        value={draft}
      />
    </SettingsRow>
  );
}
