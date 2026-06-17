/**
 * In-memory seed data for the UI-only build. There is no backend yet, so the
 * Effect services are backed by these fixtures. Values are plain decoded
 * structs; the service layer wraps reads/writes in Effect.
 */
import type { Conversation, Model } from '@/domain';

/** The model tiers shown in the selector popover, in display order. */
export const SEED_MODELS: readonly Model[] = [
  { id: 'heavy', name: 'Heavy', subtitle: 'Team of Experts', icon: 'heavy' },
  { id: 'expert', name: 'Expert', subtitle: 'Powered by Grok 4.3', icon: 'expert' },
  { id: 'fast', name: 'Fast', subtitle: 'Powered by Grok 4.3', icon: 'fast' },
  { id: 'auto', name: 'Auto', subtitle: 'Chooses Fast or Expert', icon: 'auto' },
];

/** The default selected tier on a cold start. */
export const DEFAULT_MODEL_TIER = 'auto' as const;

/** Seed conversation history, mirroring the reference history drawer. */
export const SEED_CONVERSATIONS: readonly Conversation[] = [
  { id: 'c1', title: 'Linear Tasks Check: 14 Issues', timeLabel: '7:45 PM', messages: [] },
  { id: 'c2', title: 'Display Sleep vs System Sleep on Mac', timeLabel: '12:28 AM', messages: [] },
  {
    id: 'c3',
    title: 'Blood Donation Policy Changes for Gay Men',
    timeLabel: 'Sunday',
    messages: [],
  },
  { id: 'c4', title: 'Claude Code Programmatic Workarounds', timeLabel: 'Sunday', messages: [] },
  {
    id: 'c5',
    title: 'Ambidextrous School: Dual-Hand Writing Training',
    timeLabel: 'Friday',
    messages: [],
  },
  { id: 'c6', title: 'LeetCode Hard Problems Strategy', timeLabel: 'Thursday', messages: [] },
  { id: 'c7', title: 'Google Chat vs Messages for AI Apps', timeLabel: 'Thursday', messages: [] },
  { id: 'c8', title: "AI's Role in Human Purpose", timeLabel: 'May 31', messages: [] },
  { id: 'c9', title: 'Telegram Bot Message Jump Explained', timeLabel: 'May 31', messages: [] },
  { id: 'c10', title: 'Tmux Terminal Commands Guide', timeLabel: 'May 31', messages: [] },
  { id: 'c11', title: 'Bash vs Python vs Rust for CLIs', timeLabel: 'May 30', messages: [] },
  { id: 'c12', title: 'Effect TS Dependencies Explained', timeLabel: 'May 30', messages: [] },
];

/** The account shown in the drawer header and settings. */
export const SEED_ACCOUNT = {
  name: 'Tavi',
  plan: 'X Premium+, SuperGrok',
  email: 'you@pawrrtal.ai',
} as const;
