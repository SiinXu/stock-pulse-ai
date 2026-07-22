// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { PLAYGROUND_CATALOG, PLAYGROUND_CATEGORIES } from '../catalog';
import { getMissingPlaygroundRendererIds } from '../scenarios';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const componentsRoot = path.join(sourceRoot, 'components');

function componentSourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean; isFile: () => boolean }) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : componentSourceFiles(fullPath);
    return entry.isFile() && entry.name.endsWith('.tsx') ? [fullPath] : [];
  });
}

function exportedVisualComponentNames(): string[] {
  const names = componentSourceFiles(componentsRoot).flatMap((filename) => {
    const source = fs.readFileSync(filename, 'utf8');
    return [...source.matchAll(/export\s+(?:const|function)\s+([A-Z][A-Za-z0-9_]*)/g)]
      .map((match: RegExpMatchArray) => match[1]);
  });
  return names.filter((name) => name !== 'ThemeProvider').sort();
}

describe('playground catalog', () => {
  it('uses stable, unique ids and valid source paths', () => {
    const ids = PLAYGROUND_CATALOG.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(PLAYGROUND_CATALOG).toHaveLength(139);
    for (const entry of PLAYGROUND_CATALOG) {
      expect(fs.existsSync(path.join(sourceRoot, entry.sourcePath))).toBe(true);
      expect(entry.scenarios.length).toBeGreaterThan(0);
    }
  });

  it('covers every exported visual component without duplicate aliases', () => {
    const catalogNames = PLAYGROUND_CATALOG.map((entry) => entry.name).sort();
    expect(catalogNames).toEqual(exportedVisualComponentNames());
    expect(catalogNames).not.toContain('SettingsSwitch');
    expect(catalogNames).not.toContain('TaskPanelDefault');
  });

  it('has a real renderer for every catalog entry and entries in every category', () => {
    expect(getMissingPlaygroundRendererIds()).toEqual([]);
    for (const category of PLAYGROUND_CATEGORIES) {
      expect(PLAYGROUND_CATALOG.some((entry) => entry.category === category)).toBe(true);
    }
  });
});
