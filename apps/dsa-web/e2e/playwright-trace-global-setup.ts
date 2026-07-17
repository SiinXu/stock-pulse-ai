import type { FullConfig } from '@playwright/test';
import { assertCredentialBearingFinalTracePolicy } from '../src/utils/playwrightTracePolicy';

export default function enforceFinalPlaywrightTracePolicy(config: FullConfig): void {
  assertCredentialBearingFinalTracePolicy(
    process.env,
    config.projects.map((project) => ({
      name: project.name,
      trace: project.use.trace,
    })),
  );
}
