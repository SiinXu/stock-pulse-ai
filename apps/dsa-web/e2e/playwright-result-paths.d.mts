export function resolvePlaywrightPorts(
  environment: Readonly<Record<string, string | undefined>>,
): {
  backendPort: number;
  frontendPort: number;
  fakeProviderPort: number;
  defaultRunKey: string;
};

export function resolvePlaywrightRunKey(
  requestedRunKey: string | undefined,
  defaultRunKey: string,
): string;

export function resolvePlaywrightResultDirectories(
  webRoot: string,
  runKey: string,
): { resultRoot: string; resultDir: string };
