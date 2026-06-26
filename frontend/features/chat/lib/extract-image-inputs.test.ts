import type { FileUIPart } from 'ai';
import { describe, expect, it } from 'vitest';
import { extractImageInputs, MAX_COMPOSER_IMAGES } from './extract-image-inputs';

function makeImagePart(name: string, mime: string, body = 'fake'): FileUIPart {
  const base64 = btoa(body);
  return {
    type: 'file',
    url: `data:${mime};base64,${base64}`,
    mediaType: mime,
    filename: name,
  };
}

describe('extractImageInputs', (): void => {
  it('returns empty array when no files attached', async (): Promise<void> => {
    expect(await extractImageInputs([])).toEqual([]);
  });

  it('drops non-image MIME types silently', async (): Promise<void> => {
    const txt = makeImagePart('note.txt', 'text/plain', 'hi');
    expect(await extractImageInputs([txt])).toEqual([]);
  });

  it('decodes a PNG to base64 with the data: prefix stripped', async (): Promise<void> => {
    const png = makeImagePart('a.png', 'image/png', 'PNG-BYTES');
    const result = await extractImageInputs([png]);
    expect(result).toHaveLength(1);
    expect(result[0]?.media_type).toBe('image/png');
    // "PNG-BYTES" base64 (without "data:image/png;base64," prefix).
    expect(result[0]?.data).toBe('UE5HLUJZVEVT');
    expect(result[0]?.data.startsWith('data:')).toBe(false);
  });

  it('preserves submission order across mixed MIME types', async (): Promise<void> => {
    const png = makeImagePart('a.png', 'image/png');
    const txt = makeImagePart('b.txt', 'text/plain', 'x');
    const jpg = makeImagePart('c.jpg', 'image/jpeg');
    const result = await extractImageInputs([png, txt, jpg]);
    expect(result.map((image) => image.media_type)).toEqual(['image/png', 'image/jpeg']);
  });

  it('drops unsupported image MIME types (e.g. svg)', async (): Promise<void> => {
    const svg = makeImagePart('a.svg', 'image/svg+xml');
    expect(await extractImageInputs([svg])).toEqual([]);
  });

  it('caps the result at MAX_COMPOSER_IMAGES so a malicious drop cannot blow the budget', async (): Promise<void> => {
    const tooMany = Array.from({ length: MAX_COMPOSER_IMAGES + 3 }, (_, i) => makeImagePart(`a-${i}.png`, 'image/png'));
    const result = await extractImageInputs(tooMany);
    expect(result).toHaveLength(MAX_COMPOSER_IMAGES);
  });
});
