/**
 * Parsers that turn raw `tool_result` payloads into the typed chip data the
 * chain-of-thought renderer consumes.
 *
 * @fileoverview The backend emits `tool_result` events whose `content` field
 * is a stringified JSON blob whose shape depends on the tool that produced it.
 * Each parser here is defensive: any unexpected shape returns an empty array
 * rather than throwing, because the chat stream must keep flowing even when
 * the backend tweaks a tool's response.
 */

import { KNOWN_TOOL_NAMES } from './thinking-constants';

/** A single web result chip rendered under a `web_search` tool step. */
export interface WebSourceInfo {
	/** Stable id derived from the URL, used as the React key. */
	id: string;
	/** Original URL — opened in a new tab when the chip is clicked. */
	url: string;
	/** Site hostname, used as the chip label. */
	siteName: string;
	/** Optional pretty title (falls back to `siteName`). */
	title?: string;
	/** URL to the site's favicon, served by DuckDuckGo's icon service. */
	faviconUrl?: string;
}

/** A single calendar event chip under a `calendar_search` tool step. */
export interface CalendarEventInfo {
	eventId: string;
	summary: string;
	startTime: string;
	htmlLink?: string;
}

/** A single memory chip under a `memory_search` / `summary_search` step. */
export interface MemoryResultInfo {
	meetingId: string;
	title: string;
	startTime?: string;
}

/** Aggregate of all chip arrays produced from one tool result. */
export interface ToolResultChips {
	webSources: WebSourceInfo[];
	calendarEvents: CalendarEventInfo[];
	memoryResults: MemoryResultInfo[];
}

/** Empty chip aggregate — returned for unknown / malformed results. */
const EMPTY_CHIPS: ToolResultChips = {
	webSources: [],
	calendarEvents: [],
	memoryResults: [],
};

/**
 * Parse a `tool_result.content` string into a typed JSON object, or `null` if
 * the payload isn't valid JSON. The backend always serialises tool results as
 * JSON, but we don't want a single malformed message to abort the stream.
 */
function tryParseJson(content: string): unknown {
	try {
		return JSON.parse(content);
	} catch {
		return null;
	}
}

/** Try to render a hostname out of a URL string; null when invalid. */
function safeHostname(url: string): string | null {
	try {
		return new URL(url).hostname;
	} catch {
		return null;
	}
}

/**
 * Extract web-source chips from a `web_search` tool result.
 *
 * Tolerates two on-the-wire shapes — an array of `{ citations: string[] }`
 * objects (Anthropic-style) and a flat array of URL strings — and dedupes the
 * results so the same URL never renders twice.
 */
function parseWebSearch(value: unknown): WebSourceInfo[] {
	if (!Array.isArray(value)) return [];

	const seenUrls = new Set<string>();
	const chips: WebSourceInfo[] = [];
	let index = 0;

	const pushUrl = (url: unknown): void => {
		if (typeof url !== 'string' || seenUrls.has(url)) return;
		const hostname = safeHostname(url);
		if (!hostname) return;
		seenUrls.add(url);
		chips.push({
			id: `web-${index++}`,
			url,
			siteName: hostname,
			title: hostname,
			faviconUrl: `https://icons.duckduckgo.com/ip3/${hostname}.ico`,
		});
	};

	for (const entry of value) {
		ingestWebSearchEntry(entry, pushUrl);
	}

	return chips;
}

/**
 * Push every URL inside a single `web_search` entry through `pushUrl`.
 *
 * Extracted from `parseWebSearch` to keep its nesting depth within the
 * project budget (see `scripts/check-nesting.mjs`). An entry is either
 * a bare URL string or an object with a `citations` array; anything
 * else is ignored.
 */
function ingestWebSearchEntry(entry: unknown, pushUrl: (url: unknown) => void): void {
	if (typeof entry === 'string') {
		pushUrl(entry);
		return;
	}
	if (!entry || typeof entry !== 'object' || !('citations' in entry)) return;
	const citations = (entry as { citations?: unknown }).citations;
	if (!Array.isArray(citations)) return;
	for (const url of citations) pushUrl(url);
}

/**
 * Pull the events array out of either of the two shapes the backend uses:
 * a bare array or `{ events: [...] }`. Returns an empty array on anything else.
 */
function readCalendarEventArray(value: unknown): unknown[] {
	if (Array.isArray(value)) return value;
	if (value && typeof value === 'object' && 'events' in value) {
		const events = (value as { events?: unknown }).events;
		return Array.isArray(events) ? events : [];
	}
	return [];
}

/** Map one raw calendar entry into a typed chip, or `null` when invalid. */
function toCalendarEvent(raw: unknown): CalendarEventInfo | null {
	if (!raw || typeof raw !== 'object') return null;
	const event = raw as Record<string, unknown>;
	const eventId = typeof event.event_id === 'string' ? event.event_id : null;
	const summary = typeof event.summary === 'string' ? event.summary : null;
	const startTime = typeof event.start_time === 'string' ? event.start_time : null;
	if (!(eventId && summary && startTime)) return null;
	return {
		eventId,
		summary,
		startTime,
		htmlLink: typeof event.html_link === 'string' ? event.html_link : undefined,
	};
}

/** Extract calendar event chips from a `calendar_search` tool result. */
function parseCalendarSearch(value: unknown): CalendarEventInfo[] {
	const events = readCalendarEventArray(value);
	const chips: CalendarEventInfo[] = [];
	for (const raw of events) {
		const chip = toCalendarEvent(raw);
		if (chip) chips.push(chip);
	}
	return chips;
}

/** Extract memory chips from a `memory_search` or `summary_search` result. */
function parseMemorySearch(value: unknown): MemoryResultInfo[] {
	if (!Array.isArray(value)) return [];
	const chips: MemoryResultInfo[] = [];
	for (const raw of value) {
		if (!raw || typeof raw !== 'object') continue;
		const memory = raw as Record<string, unknown>;
		const meetingId = typeof memory.meeting_id === 'string' ? memory.meeting_id : null;
		const title = typeof memory.title === 'string' ? memory.title : null;
		if (!(meetingId && title)) continue;
		chips.push({
			meetingId,
			title,
			startTime:
				typeof memory.start_time_local === 'string' ? memory.start_time_local : undefined,
		});
	}
	return chips;
}

/** Extract memory chips from a `search_chat_history` tool result. */
function parseChatHistory(value: unknown): MemoryResultInfo[] {
	if (!value || typeof value !== 'object') return [];
	const conversations = (value as { conversations?: unknown }).conversations;
	if (!Array.isArray(conversations)) return [];

	const chips: MemoryResultInfo[] = [];
	const TITLE_PREVIEW_LIMIT = 50;
	for (const raw of conversations.slice(0, 5)) {
		if (!raw || typeof raw !== 'object') continue;
		const conv = raw as Record<string, unknown>;
		const sessionId = typeof conv.session_id === 'string' ? conv.session_id : null;
		const userMessage = typeof conv.user_message === 'string' ? conv.user_message : '';
		if (!sessionId) continue;
		const previewTitle =
			userMessage.slice(0, TITLE_PREVIEW_LIMIT) +
			(userMessage.length > TITLE_PREVIEW_LIMIT ? '...' : '');
		chips.push({
			meetingId: sessionId,
			title: previewTitle || sessionId,
			startTime: typeof conv.timestamp === 'string' ? conv.timestamp : undefined,
		});
	}
	return chips;
}

/**
 * Parse a tool's result into the chip aggregate the UI consumes.
 *
 * Returns {@link EMPTY_CHIPS} for unknown tools or unparseable content so the
 * caller can blindly spread the result into props without null-guarding.
 */
export function extractToolChips(toolName: string, content: string): ToolResultChips {
	const value = tryParseJson(content);
	if (value === null) return EMPTY_CHIPS;

	switch (toolName) {
		case KNOWN_TOOL_NAMES.WEB_SEARCH:
			return { ...EMPTY_CHIPS, webSources: parseWebSearch(value) };
		case KNOWN_TOOL_NAMES.CALENDAR_SEARCH:
			return { ...EMPTY_CHIPS, calendarEvents: parseCalendarSearch(value) };
		case KNOWN_TOOL_NAMES.MEMORY_SEARCH:
		case KNOWN_TOOL_NAMES.SUMMARY_SEARCH:
			return { ...EMPTY_CHIPS, memoryResults: parseMemorySearch(value) };
		case KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY:
			return { ...EMPTY_CHIPS, memoryResults: parseChatHistory(value) };
		default:
			return EMPTY_CHIPS;
	}
}

/** Whether a chip aggregate is empty — handy for hiding source chip rows. */
function _hasAnyChip(chips: ToolResultChips): boolean {
	return (
		chips.webSources.length > 0 ||
		chips.calendarEvents.length > 0 ||
		chips.memoryResults.length > 0
	);
}
