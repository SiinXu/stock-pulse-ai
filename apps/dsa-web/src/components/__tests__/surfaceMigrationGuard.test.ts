// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const PRODUCTION_SOURCE_EXTENSIONS = new Set([
  '.cjs',
  '.css',
  '.cts',
  '.html',
  '.js',
  '.jsx',
  '.mjs',
  '.mts',
  '.ts',
  '.tsx',
]);

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

const rootSources = (fs.readdirSync('.', { withFileTypes: true }) as DirectoryEntry[])
  .filter((entry) => entry.isFile() && PRODUCTION_SOURCE_EXTENSIONS.has(sourceExtension(entry.name)))
  .map((entry) => entry.name);
const productionSourceFiles = [
  ...collectSourceFiles('src'),
  ...collectSourceFiles('public'),
  ...rootSources,
].filter(isProductionSource);
const productionSources = Object.fromEntries(productionSourceFiles.map((filename) => (
  [guardFilename(filename), fs.readFileSync(filename, 'utf8')]
)));

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
      : /\.(?:cjs|js|mjs)$/.test(filename)
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

  it('keeps production free of legacy surface debt', () => {
    const actual = inventory(Object.entries(productionSources)
      .flatMap(([filename, source]) => findLegacySurfaceDebt(filename, source)));

    expect(actual).toEqual([]);
    expect(productionSources['../../../index.html']).toContain('<div id="root"></div>');
    expect(productionSources['../../../vite.config.ts']).toContain('defineConfig');
    expect(Object.keys(productionSources).some((filename) => filename.endsWith('.css'))).toBe(true);
  });
});
