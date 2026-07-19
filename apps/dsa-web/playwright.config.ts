import { defineConfig, devices } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  resolvePlaywrightPorts,
  resolvePlaywrightResultDirectories,
} from './e2e/playwright-result-paths.mjs';
import {
  resolvePlaywrightRunKey,
  resolvePlaywrightTracePolicy,
} from './src/utils/playwrightTracePolicy';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, '../..');
const {
  backendPort,
  frontendPort,
  fakeProviderPort,
  defaultRunKey,
} = resolvePlaywrightPorts(process.env);
const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
process.env.DSA_WEB_SMOKE_PASSWORD = smokePassword;
const { requestedTraceMode } = resolvePlaywrightTracePolicy(process.env, process.argv.slice(2));

const runKey = resolvePlaywrightRunKey(process.env.DSA_WEB_E2E_RUN_ID, defaultRunKey);
const { resultDir } = resolvePlaywrightResultDirectories(currentDir, runKey);
const runtimeDir = path.join(resultDir, 'runtime');
const serviceLogDir = path.join(resultDir, 'service-logs');
console.info(
  `[playwright] run key=${runKey} ports=${frontendPort}/${backendPort}/${fakeProviderPort} results=${resultDir}`,
);

function findVenvPython() {
  let directory = repoRoot;
  while (true) {
    const unixPython = path.join(directory, '.venv', 'bin', 'python');
    if (fs.existsSync(unixPython)) {
      return `"${unixPython}"`;
    }
    const windowsPython = path.join(directory, '.venv', 'Scripts', 'python.exe');
    if (fs.existsSync(windowsPython)) {
      return `"${windowsPython}"`;
    }
    const parent = path.dirname(directory);
    if (parent === directory) {
      break;
    }
    directory = parent;
  }

  for (const candidate of ['python3', 'python']) {
    const probe = spawnSync(candidate, ['--version'], { stdio: 'ignore' });
    if (!probe.error && probe.status === 0) {
      return candidate;
    }
  }
  throw new Error('Playwright backend requires .venv Python, python3, or python on PATH.');
}

function resolveBackendCommand() {
  const python = findVenvPython();
  console.info(`[playwright] backend Python: ${python}`);
  return `${python} apps/dsa-web/e2e/run-backend-fixture.py --port ${backendPort}`;
}

export default defineConfig({
  captureGitInfo: { commit: false, diff: false },
  globalSetup: './e2e/playwright-trace-global-setup.ts',
  testDir: './e2e',
  testIgnore: process.env.DSA_WEB_E2E_INTENTIONAL_FAILURE_HARNESS === 'true'
    ? []
    : ['**/c07-failure-harness.generated.spec.ts'],
  outputDir: path.join(resultDir, 'playwright'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: path.join(resultDir, 'playwright-results.json') }],
  ],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    locale: 'zh-CN',
    trace: requestedTraceMode === 'off' ? 'off' : {
      mode: 'retain-on-failure' as const,
      screenshots: false,
      snapshots: true,
      sources: true,
      attachments: false,
    },
    screenshot: 'off',
    video: 'off',
  },
  webServer: [
    {
      command: resolveBackendCommand(),
      cwd: repoRoot,
      env: {
        ...process.env,
        DSA_WEB_E2E_LOG_DIR: serviceLogDir,
        DSA_WEB_E2E_RUNTIME_DIR: runtimeDir,
        DSA_WEB_SMOKE_PASSWORD: smokePassword,
      },
      url: `http://127.0.0.1:${backendPort}/api/v1/auth/status`,
      reuseExistingServer: false,
      timeout: 120_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
    },
    {
      command: `node e2e/run-logged-service.mjs node e2e/fake-openai-server.mjs ${fakeProviderPort}`,
      cwd: currentDir,
      env: {
        ...process.env,
        DSA_WEB_E2E_SERVICE_LOG: path.join(serviceLogDir, 'fake-provider.log'),
      },
      url: `http://127.0.0.1:${fakeProviderPort}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    },
    {
      command: `node e2e/run-logged-service.mjs npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: currentDir,
      env: {
        ...process.env,
        DSA_WEB_DEV_API_PROXY: `http://127.0.0.1:${backendPort}`,
        DSA_WEB_DISABLE_LOUPE: 'true',
        DSA_WEB_E2E_SERVICE_LOG: path.join(serviceLogDir, 'vite.log'),
      },
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
