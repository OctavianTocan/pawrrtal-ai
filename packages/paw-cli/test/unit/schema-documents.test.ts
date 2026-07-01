import { describe, expect, it } from 'vitest';
import { CliJsonSchemas, getCliJsonSchema } from '../../src/Helpers/SchemaDocuments';

describe('CLI JSON Schema documents', (): void => {
  it('exports draft 2020-12 documents for public CLI contracts', (): void => {
    expect(Object.keys(CliJsonSchemas).sort()).toEqual([
      'activeContext',
      'commandMetadata',
      'doctorReport',
      'structuredCliErrorPayload',
    ]);
    expect(getCliJsonSchema('activeContext').dialect).toBe('draft-2020-12');
    expect(getCliJsonSchema('doctorReport').schema).toEqual({ $ref: '#/$defs/DoctorReport' });
    // biome-ignore lint/complexity/useLiteralKeys: TS noPropertyAccessFromIndexSignature requires bracket access.
    expect(getCliJsonSchema('doctorReport').definitions['DoctorReport']).toMatchObject({ type: 'object' });
    expect(getCliJsonSchema('structuredCliErrorPayload').schema).toEqual({
      $ref: '#/$defs/StructuredCliErrorPayload',
    });
    // biome-ignore lint/complexity/useLiteralKeys: TS noPropertyAccessFromIndexSignature requires bracket access.
    expect(getCliJsonSchema('structuredCliErrorPayload').definitions['StructuredCliErrorPayload']).toMatchObject({
      type: 'object',
    });
  });
});
