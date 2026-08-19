// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import {
  disposePlaywrightRoutes,
  isPlaywrightTargetClosedError,
} from '../../../e2e/playwrightRouteTeardown';

const E2E_ROOT = './e2e';

function createSurface(options?: {
  closed?: boolean;
  failWith?: Error;
}) {
  const unrouteAll = vi.fn(async () => {
    if (options?.failWith) throw options.failWith;
  });
  return {
    isClosed: () => options?.closed === true,
    unrouteAll,
  };
}

describe('disposePlaywrightRoutes', () => {
  it('unroutes the open page and context with ignoreErrors before close', async () => {
    const page = createSurface();
    const context = createSurface();

    await disposePlaywrightRoutes(page, context);

    expect(page.unrouteAll).toHaveBeenCalledTimes(1);
    expect(page.unrouteAll).toHaveBeenCalledWith({ behavior: 'ignoreErrors' });
    expect(context.unrouteAll).toHaveBeenCalledTimes(1);
    expect(context.unrouteAll).toHaveBeenCalledWith({ behavior: 'ignoreErrors' });
  });

  it('skips unroute when the page is already closed', async () => {
    const page = createSurface({ closed: true });
    const context = createSurface();

    await disposePlaywrightRoutes(page, context);

    expect(page.unrouteAll).not.toHaveBeenCalled();
    expect(context.unrouteAll).toHaveBeenCalledWith({ behavior: 'ignoreErrors' });
  });

  it('swallows only the Playwright closed-target error from unrouteAll', async () => {
    const page = createSurface({
      failWith: new Error('Target page, context or browser has been closed'),
    });

    await expect(disposePlaywrightRoutes(page)).resolves.toBeUndefined();
  });

  it('does not swallow unrelated unroute failures', async () => {
    const page = createSurface({
      failWith: new Error('unroute exploded'),
    });

    await expect(disposePlaywrightRoutes(page)).rejects.toThrow('unroute exploded');
  });

  it('recognizes the closed-target teardown error', () => {
    expect(isPlaywrightTargetClosedError(
      new Error('Target page, context or browser has been closed'),
    )).toBe(true);
    expect(isPlaywrightTargetClosedError(new Error('unroute exploded'))).toBe(false);
  });
});

describe('Playwright route teardown source contract', () => {
  it('wires disposePlaywrightRoutes through the shared test auto fixture', () => {
    const source = fs.readFileSync(`${E2E_ROOT}/playwright-test.ts`, 'utf8');
    expect(source).toContain("from './playwrightRouteTeardown'");
    expect(source).toContain('disposePlaywrightRoutes(page, context)');
    expect(source).toContain('{ auto: true }');
  });

  it('requires every e2e spec to import test from the shared fixture', () => {
    const specFiles = (fs.readdirSync(E2E_ROOT) as string[])
      .filter((name: string) => name.endsWith('.spec.ts'))
      .sort();
    expect(specFiles.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const name of specFiles) {
      const source = fs.readFileSync(`${E2E_ROOT}/${name}`, 'utf8');
      const importsSharedTest = /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*['"]\.\/playwright-test(?:\.ts)?['"]/.test(source);
      const importsPackageTest = /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*['"]@playwright\/test['"]/.test(source);
      if (!importsSharedTest || importsPackageTest) {
        violations.push(name);
      }
    }

    expect(violations).toEqual([]);
  });

  it('keeps every route.fetch handler on a spec that uses the shared test', () => {
    const specFiles = (fs.readdirSync(E2E_ROOT) as string[])
      .filter((name: string) => name.endsWith('.spec.ts'))
      .sort();
    const fetchSpecs = specFiles.filter((name: string) => {
      const source = fs.readFileSync(`${E2E_ROOT}/${name}`, 'utf8');
      return /\broute\.fetch\s*\(/.test(source);
    });
    expect(fetchSpecs.length).toBeGreaterThan(0);

    const violations = fetchSpecs.filter((name: string) => {
      const source = fs.readFileSync(`${E2E_ROOT}/${name}`, 'utf8');
      return !/import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*['"]\.\/playwright-test(?:\.ts)?['"]/.test(source);
    });
    expect(violations).toEqual([]);
  });
});
