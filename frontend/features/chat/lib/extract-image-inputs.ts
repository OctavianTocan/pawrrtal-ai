/**
 * Convert composer-attached files into the wire shape the chat API
 * expects.
 *
 * The active composer (`PromptInput` / `ai-elements`) delivers each
 * attachment as a `FileUIPart` — a small descriptor holding an object
 * URL plus the source file's MIME type and filename. The backend's
 * `ChatImageInput` schema wants base64-encoded image bytes plus an
 * explicit MIME type, so this helper:
 *
 *   1. Filters down to image MIME types the provider bridge supports.
 *   2. Fetches each part's object URL, reads the response as a blob,
 *      and base64-encodes the bytes so the result fits the JSON wire
 *      shape.
 *   3. Caps the result at {@link MAX_COMPOSER_IMAGES} to mirror the
 *      backend's `MAX_IMAGES_PER_REQUEST` so a malicious or confused
 *      client can't blow the prompt budget.
 *
 * Files that don't match an allowed MIME type or that fail to read are
 * silently dropped — the user keeps any non-image attachment in the
 * composer for context, but only the supported image MIME types reach
 * the agent.
 */

import type { FileUIPart } from 'ai';
import type { ChatImageInput } from '../hooks/use-chat';

/**
 * Per-request image cap, mirrored from the backend's
 * `MAX_IMAGES_PER_REQUEST`. Bounded so a malicious / confused client
 * can't blow the prompt budget; generous enough for pasting a short
 * slideshow.
 */
export const MAX_COMPOSER_IMAGES = 8;

const ALLOWED_IMAGE_MIME_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'] as const;

type AllowedImageMimeType = (typeof ALLOWED_IMAGE_MIME_TYPES)[number];

function isAllowedImageMimeType(value: string): value is AllowedImageMimeType {
  return (ALLOWED_IMAGE_MIME_TYPES as readonly string[]).includes(value);
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i += 1) binary += String.fromCharCode(bytes[i] as number);
  return btoa(binary);
}

async function partToImageInput(part: FileUIPart): Promise<ChatImageInput | null> {
  const mime = part.mediaType;
  if (!mime || !isAllowedImageMimeType(mime)) return null;
  try {
    const response = await fetch(part.url);
    if (!response.ok) return null;
    const buffer = await response.arrayBuffer();
    const base64Payload = arrayBufferToBase64(buffer);
    if (!base64Payload) return null;
    return { data: base64Payload, media_type: mime };
  } catch {
    // Silently drop failed reads so a single bad attachment can't abort
    // the rest of the slideshow.
    return null;
  }
}

/**
 * Convert composer attachments into validated, capped {@link ChatImageInput}s.
 *
 * @param parts - The `files` array carried by `PromptInputMessage`.
 * @returns Up to {@link MAX_COMPOSER_IMAGES} validated image inputs in
 *   submission order. Returns an empty array when no attachments qualify
 *   so the caller can omit the `images` field from the wire payload.
 */
export async function extractImageInputs(parts: readonly FileUIPart[]): Promise<ChatImageInput[]> {
  // Cap the input list before reading to bound the I/O work; an over-cap
  // drag-drop shouldn't pay the cost of decoding files that would be
  // discarded anyway.
  const cappedParts = parts.slice(0, MAX_COMPOSER_IMAGES);
  const candidates = await Promise.all(cappedParts.map(partToImageInput));
  return candidates.filter((input): input is ChatImageInput => input !== null);
}
