// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const productionTs = import.meta.glob('../../**/*.ts', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionTsx = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionSources: Record<string, string> = {
  ...productionTs,
  ...productionTsx,
  '../../App.css': fs.readFileSync('src/App.css', 'utf8'),
  '../../index.css': fs.readFileSync('src/index.css', 'utf8'),
};

type MigrationOwner = 'TRACK-UI1' | 'TRACK-UI2' | 'TRACK-UI3' | 'UIUX-HARNESS';

type LegacySurfaceAllowance = {
  file: string;
  token: string;
  count: number;
  owner: MigrationOwner;
  removeBy: string;
  replacement: string;
};

const LEGACY_SURFACE_ALLOWANCES: readonly LegacySurfaceAllowance[] = [
  {
    file: '../../index.css',
    token: 'glass-card',
    count: 1,
    owner: 'UIUX-HARNESS',
    removeBy: 'UI-QA01',
    replacement: 'Delete the compatibility selector after its final page consumer migrates.',
  },
  {
    file: '../history/HistoryList.tsx',
    token: 'glass-card',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R02',
    replacement: 'Surface level="interactive" with layout-only overflow classes.',
  },
  {
    file: '../history/StockBar.tsx',
    token: 'glass-card',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R02',
    replacement: 'Surface level="interactive" with layout-only overflow classes.',
  },
  {
    file: '../run-flow/RunFlowGraph.tsx',
    token: 'ring-white/5',
    count: 2,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R03',
    replacement: 'ring-subtle.',
  },
  {
    file: '../run-flow/RunFlowSummaryBar.tsx',
    token: 'bg-surface/40',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R03',
    replacement: 'A valid semantic surface level or bg-subtle-soft.',
  },
  {
    file: '../tasks/TaskPanel.tsx',
    token: 'bg-white/8',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R03',
    replacement: 'bg-subtle.',
  },
  {
    file: '../watchlist/HomeStockWorkspace.tsx',
    token: 'glass-card',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R01',
    replacement: 'Surface level="interactive" with layout-only overflow classes.',
  },
  {
    file: '../../pages/BacktestPage.tsx',
    token: 'border-white/10',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-BT01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/BacktestPage.tsx',
    token: 'border-white/5',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-BT01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'bg-surface/25',
    count: 1,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'A valid semantic surface level or bg-subtle-soft.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'bg-white/10',
    count: 1,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'bg-subtle-hover for the hover state.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'bg-white/2',
    count: 1,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'bg-subtle-soft.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'border-white/5',
    count: 1,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'border-white/6',
    count: 5,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'border-white/8',
    count: 1,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/ChatPage.tsx',
    token: 'glass-card',
    count: 2,
    owner: 'TRACK-UI3',
    removeBy: 'UI-C01',
    replacement: 'Surface level="interactive" with layout-only overflow classes.',
  },
  {
    file: '../../pages/HomePage.tsx',
    token: 'bg-surface/60',
    count: 1,
    owner: 'TRACK-UI1',
    removeBy: 'UI-R01',
    replacement: 'A valid semantic surface level or bg-subtle.',
  },
  {
    file: '../../pages/PortfolioPage.tsx',
    token: 'bg-surface',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-P01',
    replacement: 'A valid semantic surface level or bg-subtle.',
  },
  {
    file: '../../pages/PortfolioPage.tsx',
    token: 'border-white/10',
    count: 2,
    owner: 'TRACK-UI2',
    removeBy: 'UI-P01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/PortfolioPage.tsx',
    token: 'border-white/5',
    count: 4,
    owner: 'TRACK-UI2',
    removeBy: 'UI-P01',
    replacement: 'border-subtle.',
  },
  {
    file: '../../pages/StockScreeningPage.tsx',
    token: 'bg-surface',
    count: 5,
    owner: 'TRACK-UI2',
    removeBy: 'UI-SCR01',
    replacement: 'A valid semantic surface level or bg-subtle.',
  },
  {
    file: '../../pages/StockScreeningPage.tsx',
    token: 'bg-surface/45',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-SCR01',
    replacement: 'A valid semantic surface level or bg-subtle.',
  },
  {
    file: '../../pages/StockScreeningPage.tsx',
    token: 'bg-surface/70',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-SCR01',
    replacement: 'A valid semantic surface level or bg-subtle.',
  },
];

type SurfaceDebtFinding = {
  file: string;
  line: number;
  token: string;
};

type SurfaceDebtInventory = {
  file: string;
  token: string;
  count: number;
};

const LEGACY_SURFACE_TOKEN_PATTERN = /(?<![a-zA-Z0-9_-])(?:glass-card|dashboard-card|bg-surface(?:\/[a-zA-Z0-9.[\]%-]+)?|(?:bg|border|ring)-white\/[a-zA-Z0-9.[\]%-]+)(?![a-zA-Z0-9_-])/g;

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !/\.(?:test|spec)\.[jt]sx?$/.test(filename);
}

function parseSource(filename: string, source: string): ts.SourceFile {
  return ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    filename.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function templateChunkText(node: ts.Node): string | undefined {
  if (ts.isStringLiteralLike(node)) return node.text;
  if (
    node.kind === ts.SyntaxKind.TemplateHead
    || node.kind === ts.SyntaxKind.TemplateMiddle
    || node.kind === ts.SyntaxKind.TemplateTail
  ) {
    return (node as ts.TemplateLiteralToken).text;
  }
  return undefined;
}

function findLegacySurfaceDebt(filename: string, source: string): SurfaceDebtFinding[] {
  if (filename.endsWith('.css')) {
    const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, '');
    return Array.from(withoutComments.matchAll(LEGACY_SURFACE_TOKEN_PATTERN), (match) => ({
      file: filename,
      line: withoutComments.slice(0, match.index ?? 0).split('\n').length,
      token: match[0],
    }));
  }

  const sourceFile = parseSource(filename, source);
  const findings: SurfaceDebtFinding[] = [];
  const visit = (node: ts.Node): void => {
    const text = templateChunkText(node);
    if (text !== undefined) {
      for (const match of text.matchAll(LEGACY_SURFACE_TOKEN_PATTERN)) {
        findings.push({
          file: filename,
          line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
          token: match[0],
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function inventory(findings: readonly SurfaceDebtFinding[]): SurfaceDebtInventory[] {
  const counts = new Map<string, SurfaceDebtInventory>();
  for (const finding of findings) {
    const key = `${finding.file}\u0000${finding.token}`;
    const current = counts.get(key);
    counts.set(key, {
      file: finding.file,
      token: finding.token,
      count: (current?.count ?? 0) + 1,
    });
  }
  return Array.from(counts.values()).sort((left, right) => (
    left.file.localeCompare(right.file) || left.token.localeCompare(right.token)
  ));
}

function allowanceInventory(): SurfaceDebtInventory[] {
  return LEGACY_SURFACE_ALLOWANCES
    .map(({ file, token, count }) => ({ file, token, count }))
    .sort((left, right) => left.file.localeCompare(right.file) || left.token.localeCompare(right.token));
}

describe('legacy surface migration guard', () => {
  it('detects compatibility cards, raw white-alpha colors, and the invalid surface alias', () => {
    const source = [
      "const panel = 'glass-card bg-white/5 border-white/10';",
      "const classes = active ? 'ring-white/5' : `bg-surface/${tone}`;",
      'const valid = "bg-surface-2/70 border-subtle bg-subtle-soft";',
    ].join('\n');

    expect(findLegacySurfaceDebt('../../pages/ExamplePage.tsx', source)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'glass-card' },
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'bg-white/5' },
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'border-white/10' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'ring-white/5' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'bg-surface' },
    ]);
  });

  it('detects legacy CSS selectors without treating comments as production debt', () => {
    const source = [
      '/* .glass-card is mentioned only in migration guidance. */',
      '.dashboard-card, .glass-card { background: var(--bg-card); }',
    ].join('\n');

    expect(findLegacySurfaceDebt('../../fixture.css', source).map(({ token }) => token))
      .toEqual(['dashboard-card', 'glass-card']);
  });

  it('keeps the migration inventory stable when unrelated lines move', () => {
    const legacy = "const panel = 'glass-card border-white/5';";
    const shifted = `${Array.from({ length: 400 }, (_, index) => `const value${index} = ${index};`).join('\n')}\n${legacy}`;

    expect(inventory(findLegacySurfaceDebt('../../pages/ExamplePage.tsx', shifted)))
      .toEqual(inventory(findLegacySurfaceDebt('../../pages/ExamplePage.tsx', legacy)));
  });

  it('freezes every remaining debt token by file and count with an expiring owner', () => {
    const actual = inventory(Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findLegacySurfaceDebt(filename, source)));
    const allowed = allowanceInventory();

    expect(actual).toEqual(allowed);
    expect(new Set(allowed.map(({ file, token }) => `${file}:${token}`)).size).toBe(allowed.length);
    expect(actual).not.toContainEqual(expect.objectContaining({ token: 'dashboard-card' }));
    for (const allowance of LEGACY_SURFACE_ALLOWANCES) {
      expect(allowance.owner).toMatch(/^(?:TRACK-UI[123]|UIUX-HARNESS)$/);
      expect(allowance.removeBy).toMatch(/^UI-[A-Z0-9]+$/);
      expect(allowance.replacement.length).toBeGreaterThan(0);
      expect(allowance.count).toBeGreaterThan(0);
      expect(productionSources[allowance.file], `${allowance.file} must remain in the production scan`)
        .toBeDefined();
    }
  });
});
