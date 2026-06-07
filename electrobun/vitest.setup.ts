import { tmpdir } from 'node:os';
import path from 'node:path';

process.env.XDG_DATA_HOME ??= path.join(tmpdir(), `pawrrtal-electrobun-vitest-${process.pid}`);
