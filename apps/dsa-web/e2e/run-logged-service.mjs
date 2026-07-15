import { createWriteStream, mkdirSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const [command, ...args] = process.argv.slice(2);
const logPath = process.env.DSA_WEB_E2E_SERVICE_LOG;

if (!command || !logPath) {
  process.stderr.write('Usage: DSA_WEB_E2E_SERVICE_LOG=<path> node run-logged-service.mjs <command> [args...]\n');
  process.exit(2);
}

mkdirSync(path.dirname(logPath), { recursive: true });
const log = createWriteStream(logPath, { flags: 'a' });
log.write(`[e2e-service] starting ${command} ${args.join(' ')}\n`);

const child = spawn(command, args, {
  cwd: process.cwd(),
  env: process.env,
  stdio: ['ignore', 'pipe', 'pipe'],
});

child.stdout.pipe(log, { end: false });
child.stderr.pipe(log, { end: false });

let stopping = false;
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    stopping = true;
    if (!child.killed) {
      child.kill(signal);
    }
  });
}

child.on('error', (error) => {
  log.write(`[e2e-service] failed to start: ${error.stack || error.message}\n`);
});

child.on('exit', (code, signal) => {
  log.end(`[e2e-service] exited code=${code ?? 'null'} signal=${signal ?? 'none'}\n`, () => {
    process.exitCode = stopping ? 0 : (code ?? 1);
  });
});
