#!/usr/bin/env bun

import { BunRuntime } from '@effect/platform-bun';
import { makeCli } from './Cli';

makeCli(Bun.argv.slice(2)).pipe(BunRuntime.runMain);
