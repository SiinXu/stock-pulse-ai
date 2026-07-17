import { resolvePlaywrightRunKey as resolveSharedPlaywrightRunKey } from '../../e2e/playwright-result-paths.mjs';

export type PlaywrightTraceMode = 'off' | 'retain-on-failure';

export type PlaywrightTracePolicy = {
  credentialBearingRun: boolean;
  requestedTraceMode: PlaywrightTraceMode;
};

export type PlaywrightFinalTraceProject = {
  name: string;
  trace: unknown;
};

export function resolvePlaywrightRunKey(
  requestedRunKey: string | undefined,
  defaultRunKey: string,
): string {
  return resolveSharedPlaywrightRunKey(requestedRunKey, defaultRunKey);
}

function parseCredentialBearingFlag(value: string | undefined): boolean | undefined {
  if (value === undefined) return undefined;
  if (value === 'false') return false;
  if (value === 'true') {
    return true;
  }
  throw new Error('DSA_WEB_E2E_CREDENTIAL_BEARING must be true or false.');
}

function hasKnownCredentialEnvironment(
  environment: Readonly<Record<string, string | undefined>>,
): boolean {
  return [
    environment.DSA_WEB_E2E_ALPHA_API_KEY,
    environment.DSA_PLAYWRIGHT_ARTIFACT_CANARY,
  ].some((value) => Boolean(value?.trim()));
}

function hasCliOption(argv: readonly string[], names: readonly string[]): boolean {
  return argv.some((argument) => names.some((name) => (
    argument === name || argument.startsWith(`${name}=`)
  )));
}

function traceCliOverrides(argv: readonly string[]): string[] {
  const overrides: string[] = [];
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--trace') {
      const value = argv[index + 1];
      if (!value || value.startsWith('-')) {
        overrides.push('[missing]');
      } else {
        overrides.push(value);
        index += 1;
      }
    } else if (argument.startsWith('--trace=')) {
      overrides.push(argument.slice('--trace='.length));
    }
  }
  return overrides;
}

export function resolvePlaywrightTracePolicy(
  environment: Readonly<Record<string, string | undefined>>,
  argv: readonly string[],
): PlaywrightTracePolicy {
  const requestedTraceMode = environment.DSA_WEB_E2E_TRACE ?? 'off';
  if (requestedTraceMode !== 'off' && requestedTraceMode !== 'retain-on-failure') {
    throw new Error('DSA_WEB_E2E_TRACE must be off or retain-on-failure.');
  }
  const declaredCredentialBearingRun = parseCredentialBearingFlag(
    environment.DSA_WEB_E2E_CREDENTIAL_BEARING,
  );
  const knownCredentialEnvironment = hasKnownCredentialEnvironment(environment);
  if (declaredCredentialBearingRun === false && knownCredentialEnvironment) {
    throw new Error(
      'Known Playwright credential environment values require credential-bearing mode.',
    );
  }
  const credentialBearingRun = declaredCredentialBearingRun ?? knownCredentialEnvironment;
  if (credentialBearingRun && requestedTraceMode !== 'off') {
    throw new Error('Credential-bearing Playwright runs must disable trace capture.');
  }
  if (credentialBearingRun && hasCliOption(argv, ['--ui', '--ui-host', '--ui-port'])) {
    throw new Error('Credential-bearing Playwright runs cannot use UI mode.');
  }
  if (credentialBearingRun && hasCliOption(argv, ['--config', '-c'])) {
    throw new Error('Credential-bearing Playwright runs must use the repository config.');
  }
  if (credentialBearingRun && traceCliOverrides(argv).some((value) => value !== 'off')) {
    throw new Error('Credential-bearing Playwright runs cannot enable trace capture from the CLI.');
  }
  return { credentialBearingRun, requestedTraceMode };
}

export function assertCredentialBearingFinalTracePolicy(
  environment: Readonly<Record<string, string | undefined>>,
  projects: readonly PlaywrightFinalTraceProject[],
): void {
  const { credentialBearingRun } = resolvePlaywrightTracePolicy(environment, []);
  if (!credentialBearingRun) return;
  for (const project of projects) {
    if (project.trace !== 'off') {
      throw new Error(
        `Credential-bearing Playwright project "${project.name}" resolved trace to a non-off value.`,
      );
    }
  }
}
