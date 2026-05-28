'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { toast } from '@/lib/toast';
import { attachVoiceAnalyserMeter, detachVoiceAnalyserMeter } from './voice-analyser-meter';

/** Lifecycle states the recorder cycles through. */
export type VoiceRecordingStatus =
	| 'idle'
	| 'requesting-permission'
	| 'recording'
	| 'transcribing'
	| 'error';

/** Result returned by {@link useVoiceTranscribe}. */
export interface UseVoiceTranscribeResult {
	/** Current lifecycle phase — drives the composer's mic / stop UI. */
	status: VoiceRecordingStatus;
	/** Last error message when `status === "error"`. */
	error: string | null;
	/**
	 * Normalized microphone level (0–1) while recording; near zero otherwise.
	 * Driven from a Web Audio `AnalyserNode` on the capture stream.
	 */
	meterLevel: number;
	/** Begin capturing microphone audio. Resolves once recording is live. */
	startRecording: () => Promise<void>;
	/**
	 * Stop the recorder and POST the captured blob to the backend STT proxy.
	 *
	 * Resolves with the transcript text on success, or `null` if recording
	 * was cancelled / produced no audio. Failure surfaces a toast and
	 * resolves to `null` rather than throwing — composers don't need to
	 * try/catch.
	 */
	stopRecording: () => Promise<string | null>;
	/** Discard the current recording without uploading anything. */
	cancelRecording: () => void;
}

/** MIME type the browser MediaRecorder will produce, in priority order. */
const PREFERRED_MIME_TYPES = [
	'audio/webm;codecs=opus',
	'audio/webm',
	'audio/ogg;codecs=opus',
	'audio/mp4',
] as const;

/**
 * Picks a MIME type the browser can both record AND that xAI accepts.
 * Falls back to the empty string (browser default) if none are supported,
 * which lets MediaRecorder choose for us.
 */
function pickRecorderMimeType(): string {
	if (typeof MediaRecorder === 'undefined') return '';
	for (const candidate of PREFERRED_MIME_TYPES) {
		if (MediaRecorder.isTypeSupported(candidate)) return candidate;
	}
	return '';
}

type AuthedFetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/**
 * Voice transcription is disabled on this deployment.
 *
 * The backend STT route + the 4-backend transcriber abstraction
 * (``backend/app/api/stt.py``, ``backend/app/integrations/voice/``) were
 * removed during the backend restructure. This helper now returns a clear
 * "not available" message instead of POSTing to a 404 endpoint and
 * silently failing. The composer UI and the recorder state machine are
 * unchanged so re-introducing a single backend later is a one-line flip
 * back to the network call.
 */
async function requestVoiceTranscription(
	_fetcher: AuthedFetchLike,
	_audio: Blob,
	_mimeType: string
): Promise<{ transcript: string | null; errorMessage: string | null }> {
	return {
		transcript: null,
		errorMessage:
			'Voice transcription is not available on this deployment. Type your message instead.',
	};
}

/**
 * Awaits the recorder's `stop` event with the joined audio blob.
 *
 * The latch resolver is wired into `onstop` at recorder construction time;
 * here we just plant a fresh resolver and ask the recorder to stop. Returns
 * `null` if the recorder is already inactive (defensive — shouldn't happen
 * in normal flow).
 */
function awaitFinalBlob(
	recorder: MediaRecorder,
	resolverRef: { current: ((blob: Blob | null) => void) | null }
): Promise<Blob | null> {
	return new Promise<Blob | null>((resolve) => {
		resolverRef.current = resolve;
		if (recorder.state === 'inactive') {
			resolve(null);
			return;
		}
		recorder.stop();
	});
}

/**
 * Records microphone audio and uploads it to the xAI STT proxy on stop.
 *
 * The flow:
 *   1. `startRecording()` — request mic permission, start `MediaRecorder`.
 *   2. `stopRecording()`  — stop the recorder, POST the blob to `/api/v1/stt`,
 *                            return the transcript text.
 *   3. `cancelRecording()` — abort without uploading.
 *
 * MediaRecorder is the browser's recommended capture API and works in all
 * evergreen browsers. The xAI proxy accepts the default WebM/Opus output.
 */
export function useVoiceTranscribe(): UseVoiceTranscribeResult {
	const fetcher = useAuthedFetch();
	const [status, setStatus] = useState<VoiceRecordingStatus>('idle');
	const [error, setError] = useState<string | null>(null);

	const recorderRef = useRef<MediaRecorder | null>(null);
	const streamRef = useRef<MediaStream | null>(null);
	const chunksRef = useRef<Blob[]>([]);
	const mimeTypeRef = useRef<string>('');
	const audioContextRef = useRef<AudioContext | null>(null);
	const meterRafRef = useRef<number | null>(null);
	const [meterLevel, setMeterLevel] = useState(0);
	// Latch for stopRecording's `dataavailable` → `stop` race: when the
	// recorder stops, we wait on this promise to resolve with the final
	// blob before posting. Reset every recording cycle.
	const finalBlobResolverRef = useRef<((blob: Blob | null) => void) | null>(null);

	const releaseStream = useCallback((): void => {
		detachVoiceAnalyserMeter({ audioContextRef, meterRafRef }, setMeterLevel);

		const stream = streamRef.current;
		if (stream) {
			for (const track of stream.getTracks()) {
				track.stop();
			}
		}
		streamRef.current = null;
		recorderRef.current = null;
		chunksRef.current = [];
		finalBlobResolverRef.current = null;
	}, []);

	// Always release the mic if the consumer unmounts mid-recording so we
	// don't leak the OS-level capture indicator.
	useEffect(() => {
		return () => {
			releaseStream();
		};
	}, [releaseStream]);

	const startRecording = useCallback(async (): Promise<void> => {
		if (status === 'recording' || status === 'requesting-permission') {
			return;
		}
		if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
			setStatus('error');
			setError('Microphone capture is not supported in this browser.');
			toast.error('Microphone capture is not supported in this browser.');
			return;
		}

		setStatus('requesting-permission');
		setError(null);

		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			const mimeType = pickRecorderMimeType();
			const recorder = mimeType
				? new MediaRecorder(stream, { mimeType })
				: new MediaRecorder(stream);

			chunksRef.current = [];
			mimeTypeRef.current = recorder.mimeType || mimeType || 'audio/webm';
			streamRef.current = stream;
			recorderRef.current = recorder;

			await attachVoiceAnalyserMeter(stream, { audioContextRef, meterRafRef }, setMeterLevel);

			recorder.ondataavailable = (event) => {
				if (event.data.size > 0) {
					chunksRef.current.push(event.data);
				}
			};
			recorder.onstop = () => {
				const blob =
					chunksRef.current.length > 0
						? new Blob(chunksRef.current, { type: mimeTypeRef.current })
						: null;
				finalBlobResolverRef.current?.(blob);
				finalBlobResolverRef.current = null;
			};

			// 250 ms timeslice so `stop` waits for in-flight `dataavailable` chunks.
			recorder.start(250);
			setStatus('recording');
		} catch (capturedError) {
			releaseStream();
			setStatus('error');
			const message =
				capturedError instanceof Error
					? capturedError.message
					: 'Could not start recording.';
			setError(message);
			toast.error('Microphone permission denied. Enable it in your browser settings.');
		}
	}, [releaseStream, status]);

	const stopRecording = useCallback(async (): Promise<string | null> => {
		const recorder = recorderRef.current;
		if (!recorder) return null;

		setStatus('transcribing');
		const finalBlob = await awaitFinalBlob(recorder, finalBlobResolverRef);
		releaseStream();

		if (!finalBlob || finalBlob.size === 0) {
			setStatus('idle');
			return null;
		}

		const { transcript, errorMessage } = await requestVoiceTranscription(
			fetcher,
			finalBlob,
			mimeTypeRef.current
		);
		if (errorMessage !== null) {
			setStatus('error');
			setError(errorMessage);
			toast.error('Transcription failed. Try again in a moment.');
			return null;
		}
		setStatus('idle');
		return transcript;
	}, [fetcher, releaseStream]);

	const cancelRecording = useCallback((): void => {
		const recorder = recorderRef.current;
		if (recorder && recorder.state !== 'inactive') {
			// Swallow the final blob so `stop` never triggers an upload.
			finalBlobResolverRef.current = () => {
				/* swallow */
			};
			recorder.stop();
		}
		releaseStream();
		setStatus('idle');
		setError(null);
	}, [releaseStream]);

	return { status, error, meterLevel, startRecording, stopRecording, cancelRecording };
}
