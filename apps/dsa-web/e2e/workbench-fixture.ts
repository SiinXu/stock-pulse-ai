// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Analysis Workbench disables stock search and the primary Analyze control until
 * setup/experience readiness resolves (`isExperienceModeReady` in
 * ResearchAnalysisWorkbenchPage). That flag flips only after the setup-status
 * request settles — even when tests mock a completed setup payload.
 *
 * Analyze additionally requires a non-empty `query`. StockAutocomplete may mount
 * as a fallback input while the stock index loads, then remount as a combobox;
 * fill against a soon-to-unmount node can leave React state empty. Always confirm
 * the controlled input value stuck before waiting for Analyze.
 *
 * Always wait on the real enabled state. Never use sleeps or test retries.
 */
export async function expectAnalysisWorkbenchReady(page: Page): Promise<Locator> {
  const stockSearch = page.locator('#analysis-workbench-stock-search');
  await expect(stockSearch).toBeEnabled();
  return stockSearch;
}

/**
 * Set a React-controlled text input value with a native setter + input event so
 * the parent onChange path runs even when a remount races Playwright fill.
 */
async function setControlledInputValue(locator: Locator, value: string): Promise<void> {
  await locator.evaluate((element, next) => {
    const input = element as HTMLInputElement;
    const prototype = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value');
    descriptor?.set?.call(input, next);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

export type AnalyzeButtonOptions = {
  /** Tab panel accessible name (zh default: 发起与批量). Omit to search the page. */
  tabPanelName?: string | RegExp;
  /** Button accessible name. Defaults to exact "分析" (zh professional mode). */
  buttonName?: string | RegExp;
  /** Prefer the last matching Analyze button (useful when multiple are mounted). */
  last?: boolean;
};

/**
 * Wait for workbench readiness, type a symbol, then wait for Analyze to enable.
 * Returns the enabled Analyze button locator (does not click).
 */
export async function expectAnalyzeButtonReady(
  page: Page,
  stockCode: string,
  options: AnalyzeButtonOptions = {},
): Promise<Locator> {
  const stockSearch = await expectAnalysisWorkbenchReady(page);
  // Focus first so the active StockAutocomplete instance (fallback or full)
  // receives the update. Prefer the native controlled-input path: Playwright
  // fill can land on a node that unmounts when the stock index finishes loading.
  await stockSearch.click();
  await setControlledInputValue(stockSearch, stockCode);
  await expect(stockSearch).toHaveValue(stockCode);

  const buttonName = options.buttonName ?? '分析';
  const scope = options.tabPanelName
    ? page.getByRole('tabpanel', { name: options.tabPanelName })
    : page;
  let analyze = scope.getByRole('button', {
    name: buttonName,
    exact: typeof buttonName === 'string',
  });
  if (options.last) {
    analyze = analyze.last();
  }
  await expect(analyze).toBeEnabled();
  return analyze;
}
