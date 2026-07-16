import { defineConfig, devices } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, '../..');
const backendPort = Number(process.env.DSA_WEB_SMOKE_BACKEND_PORT || 18100);
const frontendPort = Number(process.env.DSA_WEB_SMOKE_FRONTEND_PORT || 14173);
const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
process.env.DSA_WEB_SMOKE_PASSWORD = smokePassword;

const defaultRunKey = `${backendPort}-${frontendPort}-${fakeProviderPort}`;
const runKey = (process.env.DSA_WEB_E2E_RUN_ID || defaultRunKey)
  .trim()
  .replace(/[^A-Za-z0-9._-]+/g, '-');
if (!runKey) {
  throw new Error('DSA_WEB_E2E_RUN_ID must contain at least one portable filename character.');
}
const resultDir = path.join(currentDir, 'test-results', runKey);
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
  testDir: './e2e',
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
    trace: {
      mode: 'retain-on-failure',
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
