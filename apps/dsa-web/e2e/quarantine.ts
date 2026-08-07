// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { TestDetails } from '@playwright/test';

/**
 * Playwright flake quarantine helpers.
 *
 * Convention (see docs/testing-ci-gate.md → "Playwright flake quarantine"):
 * 1. Tag the test with `@quarantine` (title fragment and/or `tag`).
 * 2. Pass `quarantineDetails(issueUrl, reason)` so the tracking issue is
 *    required metadata, not optional folklore.
 * 3. Default `chromium` project uses `grepInvert: /@quarantine/` so quarantined
 *    specs leave the blocking smoke lane.
 * 4. Run the non-blocking lane with `DSA_WEB_E2E_QUARANTINE_LANE=1`
 *    (or `npm run test:smoke:quarantine`).
 *
 * Keep the quarantined set empty whenever the flake is fixed. The mechanism is
 * the deliverable; empty quarantine is healthy.
 */

const ISSUE_URL_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+\/?$/;

export function quarantineDetails(
  issueUrl: string,
  reason: string,
): Pick<TestDetails, 'tag' | 'annotation'> {
  if (!ISSUE_URL_RE.test(issueUrl)) {
    throw new Error(
      `Quarantined specs require a GitHub issue URL (got: ${JSON.stringify(issueUrl)}). `
      + 'Open a tracking issue before quarantining.',
    );
  }
  const trimmedReason = reason.trim();
  if (!trimmedReason) {
    throw new Error('Quarantined specs require a non-empty reason.');
  }

  return {
    tag: ['@quarantine'],
    annotation: [
      { type: 'quarantine', description: trimmedReason },
      { type: 'issue', description: issueUrl },
    ],
  };
}
