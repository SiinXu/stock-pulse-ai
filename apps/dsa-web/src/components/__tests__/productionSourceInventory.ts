// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />

type RawSourceInventory = Record<string, string>;

const discoveredTypeScriptSources = {
  ...import.meta.glob('../../**/*.ts', {
    eager: true,
    import: 'default',
    query: '?raw',
  }),
  ...import.meta.glob('../../**/*.tsx', {
    eager: true,
    import: 'default',
    query: '?raw',
  }),
} as RawSourceInventory;

const discoveredTsxSources = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as RawSourceInventory;

const discoveredCssSources = import.meta.glob('../../**/*.css', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as RawSourceInventory;

export function isProductionSourcePath(filename: string): boolean {
  // `src/dev/**` holds dev-only tooling (e.g. the Loupe stub and the API mock
  // switch) that is gated behind `import.meta.env.DEV` and tree-shaken out of
  // production builds. It is therefore not part of the production architecture
  // and is allowed to bridge to the `playground/` preview harness.
  return !filename.includes('/__tests__/')
    && !filename.includes('/__fixtures__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/dev/')
    && !filename.includes('/generated/')
    && !filename.includes('/stories/')
    && !/\.(?:test|spec)\.[jt]sx?$/.test(filename)
    && !/\.(?:story|stories|generated)\.[jt]sx?$/.test(filename)
    && !/\.(?:test|spec|story|stories|generated)\.css$/.test(filename);
}

function productionOnly(sources: RawSourceInventory): RawSourceInventory {
  return Object.fromEntries(
    Object.entries(sources).filter(([filename]) => isProductionSourcePath(filename)),
  );
}

export const productionTypeScriptSources = productionOnly(discoveredTypeScriptSources);
export const productionTsxSources = productionOnly(discoveredTsxSources);
export const productionCssSources = productionOnly(discoveredCssSources);
export const productionCssPaths = Object.keys(productionCssSources).sort();
export const productionCssAndTsxSources = {
  ...productionCssSources,
  ...productionTsxSources,
};
