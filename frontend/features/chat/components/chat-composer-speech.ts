/**
 * Speech recognition utilities for the chat composer.
 *
 * @fileoverview Extracted from `ChatComposerControls.tsx` so the component
 * file only exports React components (react-doctor `only-export-components`).
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Minimal browser speech-recognition surface used by the composer. */
export type BrowserSpeechRecognition = {
	continuous: boolean;
	interimResults: boolean;
	lang: string;
	start: () => void;
	stop: () => void;
	abort?: () => void;
	onend: ((event: Event) => void) | null;
	onerror: ((event: Event) => void) | null;
	onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
};

type BrowserSpeechRecognitionAlternative = {
	transcript: string;
};

type BrowserSpeechRecognitionResult = {
	readonly length: number;
	readonly isFinal: boolean;
	[index: number]: BrowserSpeechRecognitionAlternative | undefined;
};

type BrowserSpeechRecognitionResultList = {
	readonly length: number;
	[index: number]: BrowserSpeechRecognitionResult | undefined;
};

/** Browser speech-recognition result event shape used by the transcript reader. */
export type BrowserSpeechRecognitionEvent = {
	results: BrowserSpeechRecognitionResultList;
};

type BrowserSpeechRecognitionConstructor = new () => unknown;

type BrowserSpeechWindow = Window & {
	SpeechRecognition?: BrowserSpeechRecognitionConstructor;
	webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
};

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

/** Formats an elapsed recording duration as m:ss. */
export function formatRecordingTime(seconds: number): string {
	const minutes = Math.floor(seconds / 60);
	const remainingSeconds = seconds % 60;
	return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

/** Appends a voice transcript to any existing draft content. */
export function buildTranscriptContent({
	currentContent,
	transcript,
}: {
	currentContent: string;
	transcript: string;
}): string {
	const trimmedContent = currentContent.trim();
	const trimmedTranscript = transcript.trim();

	if (!trimmedContent) {
		return trimmedTranscript;
	}

	if (!trimmedTranscript) {
		return trimmedContent;
	}

	return `${trimmedContent} ${trimmedTranscript}`;
}

/** Builds fallback text for browsers without speech recognition support. */
function _fallbackTranscript(seconds: number): string {
	return `Voice note recorded for ${formatRecordingTime(seconds)}.`;
}

/** Reads the current speech-recognition transcript from a browser result event. */
function _readSpeechTranscript(event: BrowserSpeechRecognitionEvent): string {
	let nextTranscript = '';

	for (let index = 0; index < event.results.length; index++) {
		nextTranscript += event.results[index]?.[0]?.transcript ?? '';
	}

	return nextTranscript.trim();
}

/** Returns a configured speech-recognition instance when the browser supports it. */
function _getSpeechRecognition(): BrowserSpeechRecognition | null {
	if (typeof window === 'undefined') {
		return null;
	}

	const speechWindow = window as unknown as BrowserSpeechWindow;
	const SpeechRecognitionConstructor =
		speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;

	if (!SpeechRecognitionConstructor) {
		return null;
	}

	const recognition = new SpeechRecognitionConstructor() as BrowserSpeechRecognition;
	recognition.continuous = true;
	recognition.interimResults = true;
	recognition.lang = 'en-US';
	return recognition;
}
