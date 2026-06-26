/**
 * Tests for the picker's host/vendor display-label helpers.
 */

import { describe, expect, it } from 'vitest';
import { hostLabel, vendorLabel } from './model-picker-labels';

describe('hostLabel', () => {
  it('returns the canonical label for known host slugs', () => {
    expect(hostLabel('claude-code-pty')).toBe('Claude Code PTY');
    expect(hostLabel('google-ai')).toBe('Gemini API');
    expect(hostLabel('litellm')).toBe('LiteLLM');
    expect(hostLabel('opencode-go')).toBe('OpenCode Go');
    expect(hostLabel('xai')).toBe('xAI');
  });

  it('returns the raw slug for unknown hosts (no crash)', () => {
    expect(hostLabel('totally-new-host')).toBe('totally-new-host');
  });
});

describe('vendorLabel', () => {
  it('returns the canonical label for known vendor slugs', () => {
    expect(vendorLabel('anthropic')).toBe('Anthropic');
    expect(vendorLabel('openai')).toBe('OpenAI');
    expect(vendorLabel('google')).toBe('Google');
    expect(vendorLabel('xai')).toBe('xAI');
    expect(vendorLabel('zai')).toBe('Z.AI');
    expect(vendorLabel('moonshot')).toBe('Moonshot');
  });

  it('returns the raw slug for unknown vendors (no crash)', () => {
    expect(vendorLabel('brand-new')).toBe('brand-new');
  });
});
