/**
 * Web Audio RMS meter for live microphone visualization during recording.
 *
 * @fileoverview Helpers used by {@link useVoiceTranscribe}; split out to keep
 * the hook under the repository line budget for a single function.
 */

import type { Dispatch, MutableRefObject, SetStateAction } from 'react';

/** Refs owned by {@link useVoiceTranscribe} for the meter loop. */
export type VoiceAnalyserMeterRefs = {
  audioContextRef: MutableRefObject<AudioContext | null>;
  meterRafRef: MutableRefObject<number | null>;
};

/** Stops the RAF loop, closes the `AudioContext`, and clears the level. */
export function detachVoiceAnalyserMeter(
  refs: VoiceAnalyserMeterRefs,
  setMeterLevel: Dispatch<SetStateAction<number>>
): void {
  if (refs.meterRafRef.current !== null) {
    cancelAnimationFrame(refs.meterRafRef.current);
    refs.meterRafRef.current = null;
  }
  const audioContext = refs.audioContextRef.current;
  refs.audioContextRef.current = null;
  if (audioContext && audioContext.state !== 'closed') {
    void audioContext.close();
  }
  setMeterLevel(0);
}

/**
 * Hooks an `AnalyserNode` into `stream` and drives `setMeterLevel` from RMS.
 * Call {@link detachVoiceAnalyserMeter} when the capture session ends.
 */
export async function attachVoiceAnalyserMeter(
  stream: MediaStream,
  refs: VoiceAnalyserMeterRefs,
  setMeterLevel: Dispatch<SetStateAction<number>>
): Promise<void> {
  const audioContext = new AudioContext();
  refs.audioContextRef.current = audioContext;
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }
  const sourceNode = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.82;
  sourceNode.connect(analyser);

  const timeDomain = new Uint8Array(analyser.fftSize);
  const tickMeter = (): void => {
    analyser.getByteTimeDomainData(timeDomain);
    let sumSquares = 0;
    for (let index = 0; index < timeDomain.length; index += 1) {
      const sample = timeDomain[index] ?? 128;
      const normalized = (sample - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / timeDomain.length);
    const boosted = Math.min(1, rms * 5.5);
    setMeterLevel((previous) => previous * 0.55 + boosted * 0.45);
    refs.meterRafRef.current = requestAnimationFrame(tickMeter);
  };
  refs.meterRafRef.current = requestAnimationFrame(tickMeter);
}
