/**
 * Prompt input speech button.
 *
 * @fileoverview Web Speech API integration for prompt input dictation.
 */

'use client';

import { MicIcon } from 'lucide-react';
import { type ComponentProps, type RefObject, useCallback, useEffect, useReducer, useRef } from 'react';
import { cn } from '@/lib/utils';
import { PromptInputButton } from './prompt-input-layout';

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null;
  onend: ((this: SpeechRecognition, ev: Event) => void) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

type SpeechRecognitionResultList = {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
};

type SpeechRecognitionResult = {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
};

type SpeechRecognitionAlternative = {
  transcript: string;
  confidence: number;
};

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

declare global {
  interface Window {
    SpeechRecognition: {
      new (): SpeechRecognition;
    };
    webkitSpeechRecognition: {
      new (): SpeechRecognition;
    };
  }
}

type SpeechStatus = 'unsupported' | 'idle' | 'listening';
const replaceSpeechStatus = (_current: SpeechStatus, next: SpeechStatus): SpeechStatus => next;

/** Props for the speech-recognition prompt input button. */
export type PromptInputSpeechButtonProps = ComponentProps<typeof PromptInputButton> & {
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
  onTranscriptionChange?: (text: string) => void;
};

/** Button that toggles browser speech recognition for a textarea. */
export const PromptInputSpeechButton = ({
  className,
  textareaRef,
  onTranscriptionChange,
  ...props
}: PromptInputSpeechButtonProps) => {
  const [speechStatus, dispatchSpeechStatus] = useReducer(replaceSpeechStatus, 'unsupported');
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const isListening = speechStatus === 'listening';
  const isSpeechSupported = speechStatus !== 'unsupported';

  useEffect(() => {
    if (typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const speechRecognition = new SpeechRecognition();

      speechRecognition.continuous = true;
      speechRecognition.interimResults = true;
      speechRecognition.lang = 'en-US';

      speechRecognition.onstart = () => {
        dispatchSpeechStatus('listening');
      };

      speechRecognition.onend = () => {
        dispatchSpeechStatus('idle');
      };

      speechRecognition.onresult = (event) => {
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result?.isFinal) {
            finalTranscript += result[0]?.transcript ?? '';
          }
        }

        if (finalTranscript && textareaRef?.current) {
          const textarea = textareaRef.current;
          const currentValue = textarea.value;
          const newValue = currentValue + (currentValue ? ' ' : '') + finalTranscript;

          textarea.value = newValue;
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
          onTranscriptionChange?.(newValue);
        }
      };

      speechRecognition.onerror = (_event) => {
        dispatchSpeechStatus('idle');
      };

      recognitionRef.current = speechRecognition;
      dispatchSpeechStatus('idle');
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, [textareaRef, onTranscriptionChange]);

  const toggleListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }

    if (isListening) {
      recognition.stop();
    } else {
      recognition.start();
    }
  }, [isListening]);

  return (
    <PromptInputButton
      className={cn(
        'relative transition-colors duration-150 ease-out',
        isListening && 'animate-pulse bg-accent text-accent-foreground',
        className
      )}
      disabled={!isSpeechSupported}
      onClick={toggleListening}
      {...props}
    >
      <MicIcon className="size-4" />
    </PromptInputButton>
  );
};
