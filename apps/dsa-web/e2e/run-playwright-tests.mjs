import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

const argv = process.argv.slice(2);
if (argv.some((argument) => (
  argument === '--config'
  || argument.startsWith('--config=')
  || argument.startsWith('-c')
))) {
  process.stderr.write('The repository Playwright entry point does not allow alternate config files.\n');
  process.exit(2);
}

const require = createRequire(import.meta.url);
const playwrightCli = require.resolve('@playwright/test/cli');
const result = spawnSync(
  process.execPath,
  [playwrightCli, 'test', ...argv],
  { env: process.env, stdio: 'inherit' },
);
if (result.error) throw result.error;
if (result.signal) {
  process.stderr.write(`Playwright exited from signal ${result.signal}.\n`);
  process.exit(1);
}
process.exit(result.status ?? 1);
