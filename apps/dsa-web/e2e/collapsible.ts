// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, type Locator } from './playwright-test';

/**
 * Expand a shared Collapsible through its public accessible trigger.
 *
 * Product contract after the leftover-details migration: a native button named
 * with the panel title, default-closed (`aria-expanded=false`), not a
 * `<details>/<summary>` disclosure.
 */
export async function expandCollapsible(scope: Locator, title: string): Promise<Locator> {
  const trigger = scope.getByRole('button', { name: title, exact: true });
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  return trigger;
}
