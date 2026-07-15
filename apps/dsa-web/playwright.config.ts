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

// Every run gets an isolated config file. This keeps Playwright deterministic,
// avoids reading or overwriting a developer's .env, and lets first-login setup
// persist its throwaway password for the rest of the suite.
const runtimeDir = path.join(currentDir, 'test-results', 'runtime');
const e2eEnvFile = path.join(runtimeDir, 'playwright.env');
fs.mkdirSync(runtimeDir, { recursive: true });
fs.writeFileSync(
  e2eEnvFile,
  [
    'ADMIN_AUTH_ENABLED=true',
    'WEBUI_AUTO_BUILD=false',
    'SCHEDULE_ENABLED=false',
    '',
  ].join('\n'),
  'utf8',
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
      return 'python';
    }
    directory = parent;
  }
}

function resolveBackendCommand() {
  if (process.env.DSA_WEB_SMOKE_BACKEND_CMD) {
    return process.env.DSA_WEB_SMOKE_BACKEND_CMD;
  }

  return `${findVenvPython()} main.py --webui-only --host 127.0.0.1 --port ${backendPort}`;
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
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
      command: `node e2e/fake-openai-server.mjs ${fakeProviderPort}`,
      cwd: currentDir,
      url: `http://127.0.0.1:${fakeProviderPort}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: resolveBackendCommand(),
      cwd: repoRoot,
      env: {
        ...process.env,
        ENV_FILE: e2eEnvFile,
      },
      url: `http://127.0.0.1:${backendPort}/api/v1/auth/status`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: currentDir,
      env: {
        ...process.env,
        DSA_WEB_DEV_API_PROXY: `http://127.0.0.1:${backendPort}`,
      },
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
