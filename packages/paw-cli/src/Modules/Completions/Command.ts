import { Console, Effect } from 'effect';
import { Argument, Command, Completions } from 'effect/unstable/cli';
import type { CommandMetadata, CommandModule, EmptyCommandContext } from '../../Helpers/CommandMetadata';
import { applyCommandMetadata, metadataToCompletionDescriptor } from '../../Helpers/CommandMetadata';
import { ExitCode } from '../../Helpers/ExitCode';

export type CompletionShell = 'bash' | 'zsh';

/** Command metadata for generated shell completions. */
export const COMPLETIONS_METADATA = {
  name: 'completions',
  summary: 'Generate shell completions',
  description: 'Generate shell completion scripts for supported shells.',
  owner: '@pawrrtal/cli/Modules/Completions',
  arguments: [
    {
      name: 'shell',
      description: 'Shell to generate completions for',
      kind: 'choice',
      choices: ['bash', 'zsh'],
    },
  ],
  examples: [
    { command: 'paw completions bash', description: 'Print bash completions' },
    { command: 'paw completions zsh', description: 'Print zsh completions' },
  ],
  notes: ['Supported shells in this slice are `bash` and `zsh`.'],
  outputModes: ['human'],
  exitCodes: [ExitCode.success, ExitCode.usage],
} satisfies CommandMetadata;

/**
 * Builds the completions command from root command metadata.
 *
 * @param rootMetadata - Complete command tree metadata to expose to the shell.
 * @returns Effect CLI command module for shell completions.
 */
export function makeCompletionsCommand(
  rootMetadata: CommandMetadata
): CommandModule<'completions', { readonly shell: CompletionShell }, EmptyCommandContext, never, never> {
  return {
    command: applyCommandMetadata(
      Command.make(
        'completions',
        {
          shell: Argument.choice('shell', ['bash', 'zsh']),
        },
        ({ shell }) =>
          Effect.gen(function* () {
            const descriptor = metadataToCompletionDescriptor(rootMetadata);
            yield* Console.log(Completions.generate('paw', shell, descriptor));
          })
      ),
      COMPLETIONS_METADATA
    ),
    metadata: COMPLETIONS_METADATA,
  };
}
