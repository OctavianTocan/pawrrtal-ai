import { Schema } from 'effect';
import { ActiveContext } from '../Infrastructure/ActiveContext';
import { DoctorReport } from '../Modules/Doctor/Domain';
import { CommandMetadataSchema } from './CommandMetadata';
import { StructuredCliErrorPayload } from './Errors';

export const CliJsonSchemas = {
  activeContext: Schema.toJsonSchemaDocument(ActiveContext, { generateDescriptions: true }),
  commandMetadata: Schema.toJsonSchemaDocument(CommandMetadataSchema, { generateDescriptions: true }),
  doctorReport: Schema.toJsonSchemaDocument(DoctorReport, { generateDescriptions: true }),
  structuredCliErrorPayload: Schema.toJsonSchemaDocument(StructuredCliErrorPayload, { generateDescriptions: true }),
} as const;

export type CliJsonSchemaName = keyof typeof CliJsonSchemas;

/** Returns the generated JSON Schema document for a public CLI contract. */
export function getCliJsonSchema(name: CliJsonSchemaName): (typeof CliJsonSchemas)[CliJsonSchemaName] {
  return CliJsonSchemas[name];
}
