import { defineConfig, devices } from '@playwright/test';
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

const runtimeDir = path.join(currentDir, 'test-results', 'runtime');
const serviceLogDir = path.join(currentDir, 'test-results', 'service-logs');

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
      return 'python';
    }
    directory = parent;
  }
}

function resolveBackendCommand() {
  return `${findVenvPython()} apps/dsa-web/e2e/run-backend-fixture.py --port ${backendPort}`;
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    locale: 'zh-CN',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
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
