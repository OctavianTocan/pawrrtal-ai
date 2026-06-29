/**
 * Tool labels and icons used by the chain-of-thought display in the chat reply.
 *
 * @fileoverview Centralizes the present-tense ("Searching the web") and
 * past-tense ("Searched the web") labels plus the per-tool icon mapping. Pure
 * data — kept React-free so non-rendering modules can import the labels too.
 * UI imports come in via the icon `Record` exported here.
 */

import type { LucideIcon } from 'lucide-react';
import {
  BookOpenIcon,
  CalendarIcon,
  FileIcon,
  GlobeIcon,
  MessageSquareIcon,
  NotebookText,
  SearchIcon,
} from 'lucide-react';

/**
 * Backend-facing tool identifiers we render with custom labels/icons.
 *
 * Centralised so renaming a tool only requires touching this file. Anything
 * not in this list falls back to the raw tool name + the default search icon.
 */
export const KNOWN_TOOL_NAMES = {
  WEB_SEARCH: 'web_search',
  // Exa-powered web search uses `exa_search` in the app agent loop and
  // an MCP-prefixed tool ID in Claude Agent SDK. Both names share the
  // same label + icon so the UI is identical regardless of provider.
  EXA_SEARCH: 'exa_search',
  EXA_SEARCH_CLAUDE: 'mcp__pawrrtal__exa_search',
  MEMORY_SEARCH: 'memory_search',
  SUMMARY_SEARCH: 'summary_search',
  CALENDAR_SEARCH: 'calendar_search',
  FILE_SEARCH: 'file_search',
  SEARCH_CHAT_HISTORY: 'search_chat_history',
  READ_DOCUMENT: 'read_document',
  NOTION: 'ntn',
} as const;

/** Union of the tool names we ship custom UI metadata for. */
export type KnownToolName = (typeof KNOWN_TOOL_NAMES)[keyof typeof KNOWN_TOOL_NAMES];

/** Tools whose results should render as memory/meeting chips. */
const MEMORY_TOOL_NAMES = new Set<string>([
  KNOWN_TOOL_NAMES.MEMORY_SEARCH,
  KNOWN_TOOL_NAMES.SUMMARY_SEARCH,
  KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY,
]);

/**
 * Whether `toolName` searches some kind of memory store.
 * Used by the chain-of-thought renderer to pick the chip style.
 */
export function isMemoryTool(toolName: string): boolean {
  return MEMORY_TOOL_NAMES.has(toolName);
}

/** Present-tense labels rendered while a tool is running. */
const TOOL_LABELS: Record<string, string> = {
  [KNOWN_TOOL_NAMES.WEB_SEARCH]: 'Searching the web',
  [KNOWN_TOOL_NAMES.EXA_SEARCH]: 'Searching the web',
  [KNOWN_TOOL_NAMES.EXA_SEARCH_CLAUDE]: 'Searching the web',
  [KNOWN_TOOL_NAMES.MEMORY_SEARCH]: 'Searching memory',
  [KNOWN_TOOL_NAMES.SUMMARY_SEARCH]: 'Searching memory',
  [KNOWN_TOOL_NAMES.CALENDAR_SEARCH]: 'Checking the calendar',
  [KNOWN_TOOL_NAMES.FILE_SEARCH]: 'Searching files',
  [KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY]: 'Searching chat history',
  [KNOWN_TOOL_NAMES.READ_DOCUMENT]: 'Reading document',
  [KNOWN_TOOL_NAMES.NOTION]: 'Running Notion command',
};

/** Past-tense labels rendered once a tool has finished. */
const TOOL_LABELS_PAST: Record<string, string> = {
  [KNOWN_TOOL_NAMES.WEB_SEARCH]: 'Searched the web',
  [KNOWN_TOOL_NAMES.EXA_SEARCH]: 'Searched the web',
  [KNOWN_TOOL_NAMES.EXA_SEARCH_CLAUDE]: 'Searched the web',
  [KNOWN_TOOL_NAMES.MEMORY_SEARCH]: 'Searched memory',
  [KNOWN_TOOL_NAMES.SUMMARY_SEARCH]: 'Searched memory',
  [KNOWN_TOOL_NAMES.CALENDAR_SEARCH]: 'Checked the calendar',
  [KNOWN_TOOL_NAMES.FILE_SEARCH]: 'Searched files',
  [KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY]: 'Searched chat history',
  [KNOWN_TOOL_NAMES.READ_DOCUMENT]: 'Read document',
  [KNOWN_TOOL_NAMES.NOTION]: 'Ran Notion command',
};

/** Lucide icons keyed by tool name — fall back to {@link SearchIcon}. */
const TOOL_ICONS: Record<string, LucideIcon> = {
  [KNOWN_TOOL_NAMES.WEB_SEARCH]: GlobeIcon,
  [KNOWN_TOOL_NAMES.EXA_SEARCH]: GlobeIcon,
  [KNOWN_TOOL_NAMES.EXA_SEARCH_CLAUDE]: GlobeIcon,
  [KNOWN_TOOL_NAMES.MEMORY_SEARCH]: SearchIcon,
  [KNOWN_TOOL_NAMES.SUMMARY_SEARCH]: BookOpenIcon,
  [KNOWN_TOOL_NAMES.CALENDAR_SEARCH]: CalendarIcon,
  [KNOWN_TOOL_NAMES.FILE_SEARCH]: FileIcon,
  [KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY]: MessageSquareIcon,
  [KNOWN_TOOL_NAMES.READ_DOCUMENT]: FileIcon,
  [KNOWN_TOOL_NAMES.NOTION]: NotebookText,
};

/** Get the present-tense label for a tool, or its raw name if unknown. */
export function getToolLabel(toolName: string): string {
  return TOOL_LABELS[toolName] ?? toolName;
}

/** Get the past-tense label for a tool, or its raw name if unknown. */
export function getCompletedToolLabel(toolName: string): string {
  return TOOL_LABELS_PAST[toolName] ?? toolName;
}

/** Get the Lucide icon component for a tool, defaulting to the search icon. */
export function getToolIcon(toolName: string): LucideIcon {
  return TOOL_ICONS[toolName] ?? SearchIcon;
}

/** Maximum number of result chips to show inline before "+N more" overflow. */
export const MAX_VISIBLE_RESULTS = 3;
