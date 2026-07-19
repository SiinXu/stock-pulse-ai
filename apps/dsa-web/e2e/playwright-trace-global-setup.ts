// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
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
