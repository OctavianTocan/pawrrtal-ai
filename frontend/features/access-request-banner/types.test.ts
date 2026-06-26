import { describe, expect, it } from 'vitest';
import { BOUNCY_SPRING, EXPAND_SPRING, getInitials } from './types';

describe('getInitials', () => {
  it('returns up to two initials from a full name', () => {
    expect(getInitials('Octavian Tocan')).toBe('OT');
  });

  it('returns one initial when only one name token exists', () => {
    expect(getInitials('Jane')).toBe('J');
  });

  it('returns empty string for empty / whitespace input', () => {
    expect(getInitials('')).toBe('');
    expect(getInitials('   ')).toBe('');
  });

  it('upper-cases the result regardless of input casing', () => {
    expect(getInitials('alice bob')).toBe('AB');
  });

  it('caps at 2 characters even with 3+ name tokens', () => {
    expect(getInitials('John Quincy Adams')).toBe('JQ');
  });
});

describe('spring presets', () => {
  it('exposes the bouncy + expand spring configs as readonly objects', () => {
    expect(BOUNCY_SPRING.type).toBe('spring');
    expect(EXPAND_SPRING.type).toBe('spring');
    expect(BOUNCY_SPRING.damping).toBeGreaterThan(0);
    expect(EXPAND_SPRING.damping).toBeGreaterThan(BOUNCY_SPRING.damping);
  });
});
