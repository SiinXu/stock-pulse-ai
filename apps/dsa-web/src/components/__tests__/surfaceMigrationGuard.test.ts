// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const PRODUCTION_SOURCE_EXTENSIONS = new Set(['.css', '.html', '.js', '.jsx', '.ts', '.tsx']);

type DirectoryEntry = {
  name: string;
  isDirectory: () => boolean;
  isFile: () => boolean;
};

function sourceExtension(filename: string): string {
  const extensionIndex = filename.lastIndexOf('.');
  return extensionIndex === -1 ? '' : filename.slice(extensionIndex);
}

function collectSourceFiles(root: string): string[] {
  if (!fs.existsSync(root)) return [];
  const entries = fs.readdirSync(root, { withFileTypes: true }) as DirectoryEntry[];
  return entries.flatMap((entry) => {
    const filename = `${root}/${entry.name}`;
    if (entry.isDirectory()) return collectSourceFiles(filename);
    return PRODUCTION_SOURCE_EXTENSIONS.has(sourceExtension(entry.name)) ? [filename] : [];
  });
}

function guardFilename(filename: string): string {
  if (filename.startsWith('src/components/')) {
    return `../${filename.slice('src/components/'.length)}`;
  }
  if (filename.startsWith('src/')) {
    return `../../${filename.slice('src/'.length)}`;
  }
  return `../../../${filename}`;
}

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !/\.(?:test|spec)\.(?:[jt]sx?|css|html)$/.test(filename);
}

const rootStyleAndMarkup = (fs.readdirSync('.', { withFileTypes: true }) as DirectoryEntry[])
  .filter((entry) => entry.isFile() && ['.css', '.html'].includes(sourceExtension(entry.name)))
  .map((entry) => entry.name);
const productionSourceFiles = [
  ...collectSourceFiles('src'),
  ...collectSourceFiles('public'),
  ...rootStyleAndMarkup,
].filter(isProductionSource);
const productionSources = Object.fromEntries(productionSourceFiles.map((filename) => (
  [guardFilename(filename), fs.readFileSync(filename, 'utf8')]
)));

type MigrationOwner = 'TRACK-UI1' | 'TRACK-UI2' | 'TRACK-UI3' | 'UIUX-HARNESS';

type LegacySurfaceAllowance = {
  file: string;
  token: string;
  count: number;
  owner: MigrationOwner;
  removeBy: string;
  replacement: string;
  contexts?: readonly {
    occurrence: number;
    nearby: string;
    replacement: string;
  }[];
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
    replacement: 'Map each panel by task semantics; do not preserve one card treatment for both.',
    contexts: [
      {
        occurrence: 1,
        nearby: 'DeepResearchPanel',
        replacement: 'Surface level="interactive" for the independent Research task panel.',
      },
      {
        occurrence: 2,
        nearby: 'chat-message-scroll',
        replacement: 'Surface level="canvas" for the flat message canvas.',
      },
    ],
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

function parseSource(filename: string, source: string): ts.SourceFile {
  const scriptKind = filename.endsWith('.tsx')
    ? ts.ScriptKind.TSX
    : filename.endsWith('.jsx')
      ? ts.ScriptKind.JSX
      : filename.endsWith('.js')
        ? ts.ScriptKind.JS
        : ts.ScriptKind.TS;
  return ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    scriptKind,
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
  if (filename.endsWith('.css') || filename.endsWith('.html')) {
    const withoutComments = source
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/<!--[\s\S]*?-->/g, '');
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
  return inventory(LEGACY_SURFACE_ALLOWANCES.flatMap(({ file, token, count }) => (
    Array.from({ length: count }, () => ({ file, token, line: 0 }))
  )));
}

function tokenOffsets(source: string, token: string): number[] {
  const offsets: number[] = [];
  let offset = source.indexOf(token);
  while (offset !== -1) {
    offsets.push(offset);
    offset = source.indexOf(token, offset + token.length);
  }
  return offsets;
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

  it('detects debt in the production HTML entry without scanning comments', () => {
    const source = [
      '<!-- <main class="glass-card">Old example</main> -->',
      '<main class="bg-white/5 border-white/10">Content</main>',
    ].join('\n');

    expect(findLegacySurfaceDebt('../../../fixture.html', source).map(({ token }) => token))
      .toEqual(['bg-white/5', 'border-white/10']);
  });

  it('keeps the migration inventory stable when unrelated lines move', () => {
    const legacy = "const panel = 'glass-card border-white/5';";
    const shifted = `${Array.from({ length: 400 }, (_, index) => `const value${index} = ${index};`).join('\n')}\n${legacy}`;

    expect(inventory(findLegacySurfaceDebt('../../pages/ExamplePage.tsx', shifted)))
      .toEqual(inventory(findLegacySurfaceDebt('../../pages/ExamplePage.tsx', legacy)));
  });

  it('freezes every remaining debt token by file and count with an expiring owner', () => {
    const actual = inventory(Object.entries(productionSources)
      .flatMap(([filename, source]) => findLegacySurfaceDebt(filename, source)));
    const allowed = allowanceInventory();

    expect(actual).toEqual(allowed);
    expect(new Set(LEGACY_SURFACE_ALLOWANCES.map(({ file, token }) => `${file}:${token}`)).size)
      .toBe(LEGACY_SURFACE_ALLOWANCES.length);
    expect(actual).not.toContainEqual(expect.objectContaining({ token: 'dashboard-card' }));
    expect(productionSources['../../../index.html']).toContain('<div id="root"></div>');
    expect(Object.keys(productionSources).some((filename) => filename.endsWith('.css'))).toBe(true);
    for (const allowance of LEGACY_SURFACE_ALLOWANCES) {
      expect(allowance.owner).toMatch(/^(?:TRACK-UI[123]|UIUX-HARNESS)$/);
      expect(allowance.removeBy).toMatch(/^UI-[A-Z0-9]+$/);
      expect(allowance.replacement.length).toBeGreaterThan(0);
      expect(allowance.count).toBeGreaterThan(0);
      expect(productionSources[allowance.file], `${allowance.file} must remain in the production scan`)
        .toBeDefined();
      if (allowance.contexts) {
        expect(allowance.contexts).toHaveLength(allowance.count);
        const source = productionSources[allowance.file];
        const offsets = tokenOffsets(source, allowance.token);
        for (const context of allowance.contexts) {
          expect(context.occurrence).toBeGreaterThan(0);
          expect(context.replacement.length).toBeGreaterThan(0);
          const offset = offsets[context.occurrence - 1];
          expect(offset).toBeDefined();
          expect(source.slice(offset, offset + 800)).toContain(context.nearby);
        }
      }
    }
  });
});
