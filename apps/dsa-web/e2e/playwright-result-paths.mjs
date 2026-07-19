import fs from 'node:fs';
import path from 'node:path';

export function resolvePlaywrightPorts(environment) {
  const backendPort = Number(environment.DSA_WEB_SMOKE_BACKEND_PORT || 18100);
  const frontendPort = Number(environment.DSA_WEB_SMOKE_FRONTEND_PORT || 14173);
  const fakeProviderPort = Number(environment.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
  return {
    backendPort,
    frontendPort,
    fakeProviderPort,
    defaultRunKey: `${backendPort}-${frontendPort}-${fakeProviderPort}`,
  };
}

export function resolvePlaywrightRunKey(requestedRunKey, defaultRunKey) {
  const runKey = (requestedRunKey || defaultRunKey)
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, '-');
  if (!runKey || runKey === '.' || runKey === '..') {
    throw new Error(
      'DSA_WEB_E2E_RUN_ID must resolve to one portable test-results child directory.',
    );
  }
  return runKey;
}

function assertNotSymbolicLink(candidate, label) {
  try {
    if (fs.lstatSync(candidate).isSymbolicLink()) {
      throw new Error(`${label} cannot be a symbolic link.`);
    }
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }
}

export function resolvePlaywrightResultDirectories(webRoot, runKey) {
  const resultRoot = path.resolve(webRoot, 'test-results');
  const resultDir = path.resolve(resultRoot, runKey);
  if (path.dirname(resultDir) !== resultRoot) {
    throw new Error(
      'DSA_WEB_E2E_RUN_ID must stay inside the Playwright test-results directory.',
    );
  }
  assertNotSymbolicLink(resultRoot, 'Playwright test-results directory');
  assertNotSymbolicLink(resultDir, 'Playwright run directory');
  return { resultRoot, resultDir };
}
