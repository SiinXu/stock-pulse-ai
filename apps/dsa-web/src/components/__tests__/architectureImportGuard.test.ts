// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import {
  isProductionSourcePath,
  productionTypeScriptSources,
} from './productionSourceInventory';

type ArchitectureRule =
  | 'common-to-ui-owner'
  | 'lower-layer-to-composition'
  | 'non-view-to-ui'
  | 'page-to-page'
  | 'production-to-playground';

type DependencyKind = 'dynamic-import' | 'export' | 'import' | 'import-type' | 'require';

type ArchitectureImportFinding = {
  source: string;
  target: string;
  line: number;
  kind: DependencyKind;
  rule: ArchitectureRule;
};

type ArchitectureImportAllowance = Omit<ArchitectureImportFinding, 'line'> & {
  owner: 'Track W2';
  removeWhen: string;
};

const INVENTORY_DIRECTORY = ['components', '__tests__'];
const NON_VIEW_ROOTS = new Set([
  'api',
  'contexts',
  'hooks',
  'i18n',
  'locales',
  'stores',
  'types',
  'utils',
]);
const UI_ROOTS = new Set(['components', 'pages', 'playground']);
const MAX_ARCHITECTURE_IMPORT_ALLOWANCES = 8;

const ARCHITECTURE_IMPORT_ALLOWANCES: readonly ArchitectureImportAllowance[] = [
  {
    source: 'components/common/index.ts',
    target: 'components/layout/Shell.tsx',
    kind: 'export',
    rule: 'common-to-ui-owner',
    owner: 'Track W2',
    removeWhen: 'W2b switches Shell consumers to its layout owner and removes the foreign re-export.',
  },
  {
    source: 'components/common/index.ts',
    target: 'components/layout/SidebarNav.tsx',
    kind: 'export',
    rule: 'common-to-ui-owner',
    owner: 'Track W2',
    removeWhen: 'W2b removes the unused foreign SidebarNav re-export.',
  },
  {
    source: 'components/common/index.ts',
    target: 'components/theme/ThemeProvider.tsx',
    kind: 'export',
    rule: 'common-to-ui-owner',
    owner: 'Track W2',
    removeWhen: 'W2b removes the unused foreign ThemeProvider re-export.',
  },
  {
    source: 'components/common/index.ts',
    target: 'components/theme/ThemeToggle.tsx',
    kind: 'export',
    rule: 'common-to-ui-owner',
    owner: 'Track W2',
    removeWhen: 'W2b switches ThemeToggle consumers to its theme owner and removes the foreign re-export.',
  },
  {
    source: 'hooks/useRouteFocusTarget.ts',
    target: 'components/routing/routeFocusContext.ts',
    kind: 'import',
    rule: 'non-view-to-ui',
    owner: 'Track W2',
    removeWhen: 'W2c moves the route-focus context contract to neutral context ownership.',
  },
  {
    source: 'hooks/useRouteFocusTarget.ts',
    target: 'components/routing/routeFocusContext.ts',
    kind: 'export',
    rule: 'non-view-to-ui',
    owner: 'Track W2',
    removeWhen: 'W2c moves the RouteFocusTarget type to neutral context ownership.',
  },
  {
    source: 'hooks/useSystemConfig.ts',
    target: 'components/settings/settingsSubCategories.ts',
    kind: 'import',
    rule: 'non-view-to-ui',
    owner: 'Track W2',
    removeWhen: 'A dedicated Settings contract slice extracts the cohesive subcategory policy from presentation ownership.',
  },
  {
    source: 'utils/connectionSchemaAuthority.ts',
    target: 'components/settings/modelAccessFieldKey.ts',
    kind: 'import',
    rule: 'non-view-to-ui',
    owner: 'Track W2',
    removeWhen: 'W2c moves the model-access field-key contract to neutral utility ownership.',
  },
];

function normalizePathSegments(segments: readonly string[]): string {
  const normalized: string[] = [];
  for (const segment of segments) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      normalized.pop();
      continue;
    }
    normalized.push(segment);
  }
  return normalized.join('/');
}

function inventoryKeyToSourcePath(filename: string): string {
  return normalizePathSegments([...INVENTORY_DIRECTORY, ...filename.split('/')]);
}

const sourcePathByInventoryKey = new Map(
  Object.keys(productionTypeScriptSources).map((filename) => [
    filename,
    inventoryKeyToSourcePath(filename),
  ]),
);
const productionSourcePaths = new Set(sourcePathByInventoryKey.values());

function resolveInternalImport(source: string, specifier: string): string | undefined {
  if (!specifier.startsWith('.')) return undefined;
  const cleanSpecifier = specifier.split(/[?#]/, 1)[0] ?? specifier;
  const sourceDirectory = source.split('/').slice(0, -1);
  const base = normalizePathSegments([...sourceDirectory, ...cleanSpecifier.split('/')]);
  const extensionlessBase = base.replace(/\.(?:js|jsx)$/, '');
  const candidates = /\.(?:ts|tsx)$/.test(base)
    ? [base]
    : [
        `${extensionlessBase}.ts`,
        `${extensionlessBase}.tsx`,
        `${extensionlessBase}/index.ts`,
        `${extensionlessBase}/index.tsx`,
      ];
  return candidates.find((candidate) => productionSourcePaths.has(candidate));
}

function architectureRuleFor(source: string, target: string): ArchitectureRule | undefined {
  const sourceParts = source.split('/');
  const targetParts = target.split('/');
  const sourceRoot = sourceParts[0];
  const targetRoot = targetParts[0];

  if (targetRoot === 'playground' && sourceRoot !== 'playground' && source !== 'App.tsx') {
    return 'production-to-playground';
  }
  if (sourceRoot === 'pages' && targetRoot === 'pages') {
    return 'page-to-page';
  }
  if (
    (targetRoot === 'pages' && source !== 'App.tsx')
    || (target === 'App.tsx' && source !== 'main.tsx' && source !== 'App.tsx')
    || (target === 'main.tsx' && source !== 'main.tsx')
  ) {
    return 'lower-layer-to-composition';
  }
  if (
    sourceParts[0] === 'components'
    && sourceParts[1] === 'common'
    && targetParts[0] === 'components'
    && targetParts[1] !== 'common'
  ) {
    return 'common-to-ui-owner';
  }
  if (NON_VIEW_ROOTS.has(sourceRoot) && UI_ROOTS.has(targetRoot)) {
    return 'non-view-to-ui';
  }
  return undefined;
}

function staticSpecifier(expression: ts.Expression | undefined): string | undefined {
  return expression && (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression))
    ? expression.text
    : undefined;
}

function findArchitectureImportViolations(
  source: string,
  sourceText: string,
): ArchitectureImportFinding[] {
  const sourceFile = ts.createSourceFile(
    source,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    source.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const findings: ArchitectureImportFinding[] = [];

  const record = (node: ts.Node, specifier: string | undefined, kind: DependencyKind): void => {
    if (!specifier) return;
    const target = resolveInternalImport(source, specifier);
    if (!target) return;
    const rule = architectureRuleFor(source, target);
    if (!rule) return;
    findings.push({
      source,
      target,
      line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
      kind,
      rule,
    });
  };

  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node)) {
      record(node, staticSpecifier(node.moduleSpecifier), 'import');
    } else if (ts.isExportDeclaration(node)) {
      record(node, staticSpecifier(node.moduleSpecifier), 'export');
    } else if (ts.isImportTypeNode(node)) {
      const argument = node.argument;
      record(
        node,
        ts.isLiteralTypeNode(argument) ? staticSpecifier(argument.literal) : undefined,
        'import-type',
      );
    } else if (ts.isCallExpression(node)) {
      if (node.expression.kind === ts.SyntaxKind.ImportKeyword) {
        record(node, staticSpecifier(node.arguments[0]), 'dynamic-import');
      } else if (ts.isIdentifier(node.expression) && node.expression.text === 'require') {
        record(node, staticSpecifier(node.arguments[0]), 'require');
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function findingKey(finding: Omit<ArchitectureImportFinding, 'line'>): string {
  return [finding.rule, finding.source, finding.kind, finding.target].join(' | ');
}

describe('frontend architecture import guard', () => {
  it('uses one production inventory that excludes test and generated sources', () => {
    expect(isProductionSourcePath('../../pages/HomePage.tsx')).toBe(true);
    expect(isProductionSourcePath('../../pages/HomePage.test.tsx')).toBe(false);
    expect(isProductionSourcePath('../../pages/HomePage.stories.tsx')).toBe(false);
    expect(isProductionSourcePath('../../components/__tests__/Fixture.tsx')).toBe(false);
    expect(isProductionSourcePath('../../components/fixtures/Fixture.tsx')).toBe(false);
    expect(isProductionSourcePath('../../i18n/generated/catalog.ts')).toBe(false);
    expect(Object.keys(productionTypeScriptSources).length).toBeGreaterThan(0);
    expect(Object.keys(productionTypeScriptSources).every(isProductionSourcePath)).toBe(true);
  });

  it('detects each enforced dependency direction and leaves valid composition alone', () => {
    expect(findArchitectureImportViolations(
      'pages/FixturePage.tsx',
      "import { HomePage } from './HomePage';",
    )).toEqual([expect.objectContaining({ rule: 'page-to-page' })]);
    expect(findArchitectureImportViolations(
      'components/watchlist/Fixture.tsx',
      "import HomePage from '../../pages/HomePage';",
    )).toEqual([expect.objectContaining({ rule: 'lower-layer-to-composition' })]);
    expect(findArchitectureImportViolations(
      'utils/fixture.ts',
      "import App from '../App';",
    )).toEqual([expect.objectContaining({ rule: 'lower-layer-to-composition' })]);
    expect(findArchitectureImportViolations(
      'hooks/fixture.ts',
      "import '../main';",
    )).toEqual([expect.objectContaining({ rule: 'lower-layer-to-composition' })]);
    expect(findArchitectureImportViolations(
      'components/common/Fixture.ts',
      "export { Shell } from '../layout/Shell';",
    )).toEqual([expect.objectContaining({ rule: 'common-to-ui-owner' })]);
    expect(findArchitectureImportViolations(
      'utils/fixture.ts',
      "const Settings = import('../components/settings/SettingsSectionCard');",
    )).toEqual([expect.objectContaining({ rule: 'non-view-to-ui', kind: 'dynamic-import' })]);
    expect(findArchitectureImportViolations(
      'components/watchlist/Fixture.tsx',
      "import Catalog from '../../playground/ComponentPlaygroundPage';",
    )).toEqual([expect.objectContaining({ rule: 'production-to-playground' })]);
    expect(findArchitectureImportViolations(
      'App.tsx',
      "import { SettingsPage } from './pages/SettingsPage';",
    )).toEqual([]);
    expect(findArchitectureImportViolations(
      'main.tsx',
      "import App from './App';",
    )).toEqual([]);
    expect(findArchitectureImportViolations(
      'App.tsx',
      "const Catalog = import('./playground/ComponentPlaygroundPage');",
    )).toEqual([]);
  });

  it('covers type imports, require calls, and Vite query suffixes', () => {
    const findings = findArchitectureImportViolations(
      'utils/fixture.ts',
      [
        "type Field = import('../components/settings/SettingsField').SettingsFieldProps;",
        "const section = require('../components/settings/SettingsSectionCard?raw');",
      ].join('\n'),
    );

    expect(findings).toEqual([
      expect.objectContaining({ kind: 'import-type', rule: 'non-view-to-ui' }),
      expect.objectContaining({ kind: 'require', rule: 'non-view-to-ui' }),
    ]);
  });

  it('keeps production dependencies within the documented direction contract', () => {
    const actualFindings = Object.entries(productionTypeScriptSources)
      .flatMap(([inventoryKey, sourceText]) => {
        const source = sourcePathByInventoryKey.get(inventoryKey);
        if (!source) throw new Error(`Architecture guard lost ${inventoryKey}.`);
        return findArchitectureImportViolations(source, sourceText);
      });
    const actualKeys = actualFindings.map(findingKey).sort();
    const allowanceKeys = ARCHITECTURE_IMPORT_ALLOWANCES.map(findingKey).sort();

    expect(new Set(allowanceKeys).size).toBe(allowanceKeys.length);
    expect(ARCHITECTURE_IMPORT_ALLOWANCES.length)
      .toBeLessThanOrEqual(MAX_ARCHITECTURE_IMPORT_ALLOWANCES);
    expect(ARCHITECTURE_IMPORT_ALLOWANCES.every(({ owner, removeWhen }) => (
      owner === 'Track W2' && removeWhen.trim().length > 0
    ))).toBe(true);
    expect(actualKeys).toEqual(allowanceKeys);
  });
});
