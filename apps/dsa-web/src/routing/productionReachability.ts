// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { APP_ROUTE_PATHS } from './routes';

/**
 * Production reachability inventory for shipped Page/Panel/Workspace/Widget
 * surfaces (Refs #1058 / #1008). A capability is reachable when a value import
 * chain from App.tsx route table reaches its module. Unreachable leftovers are
 * frozen in UNREACHABLE_CAPABILITY_LEDGER (shrink-only).
 */

export type NamedBoardCapability = {
  id: string;
  component: string;
  file: string;
};

export type UnreachableCapabilityLedgerEntry = {
  id: string;
  component: string;
  file: string;
  reason: string;
  removeWhen: string;
};

export type AppRouteBinding = {
  ident: string;
  module: string;
  routeKey: string;
  route: string;
};

export type ReachabilityInventoryEntry = {
  file: string;
  component: string;
  route: string;
  routeKey: string;
};

export const PRODUCT_SURFACE_SUFFIXES = [
  'Page.tsx',
  'Panel.tsx',
  'Workspace.tsx',
  'Widget.tsx',
] as const;

/** Shrink-only. Do not raise this to absorb a new unreachable surface. */
export const UNREACHABLE_CAPABILITY_LEDGER_CEILING = 2;

/**
 * Issue #1058 / #1008 named product capabilities that must stay on a real
 * production route. Host files are the implementation modules, not Playground.
 */
export const NAMED_BOARD_CAPABILITIES: readonly NamedBoardCapability[] = [
  { id: 'todays-focus', component: 'TodaysFocusPanel', file: 'components/home/TodaysFocusPanel.tsx' },
  { id: 'watchlist-score-column', component: 'WatchlistScoreColumn', file: 'components/watchlist/WatchlistScoreColumn.tsx' },
  { id: 'dcf-sensitivity', component: 'DcfSensitivityPanel', file: 'components/valuation/DcfSensitivityPanel.tsx' },
  { id: 'report-export', component: 'ReportMarkdownPanel', file: 'components/report/ReportMarkdownPanel.tsx' },
  { id: 'report-version-compare', component: 'ReportVersionCompareView', file: 'components/report-version-compare/ReportVersionCompareView.tsx' },
  { id: 'decision-signal-outcome-stats', component: 'DecisionSignalOutcomeStatsCard', file: 'components/decision-signals/DecisionSignalOutcomeStatsCard.tsx' },
  { id: 'event-calendar', component: 'EventCalendarWorkspace', file: 'components/event-calendar/EventCalendarWorkspace.tsx' },
  { id: 'event-alerts', component: 'EventAlertsPanel', file: 'components/event-alerts/EventAlertsPanel.tsx' },
  { id: 'zero-config-first-run', component: 'ZeroConfigFirstRunPanel', file: 'components/onboarding/ZeroConfigFirstRunPanel.tsx' },
  { id: 'portfolio-health', component: 'PortfolioHealthPanel', file: 'components/portfolio-insights/PortfolioHealthPanel.tsx' },
  { id: 'portfolio-stress', component: 'PortfolioStressPanel', file: 'components/portfolio-insights/PortfolioStressPanel.tsx' },
  { id: 'portfolio-risk', component: 'PortfolioRiskMetricsPanel', file: 'components/portfolio-risk/PortfolioRiskMetricsPanel.tsx' },
  { id: 'reasoning-trace-export', component: 'ReasoningTraceExportControls', file: 'components/report/ReasoningTraceExportControls.tsx' },
  { id: 'kline-chart', component: 'KlineChart', file: 'components/charts/KlineChart.tsx' },
  { id: 'risk-heatmap', component: 'RiskHeatmap', file: 'components/charts/RiskHeatmap.tsx' },
  { id: 'loaded-extensions', component: 'LoadedExtensionsPanel', file: 'components/settings/LoadedExtensionsPanel.tsx' },
  { id: 'scheduled-tasks', component: 'ScheduledTasksPanel', file: 'components/settings/ScheduledTasksPanel.tsx' },
  { id: 'data-providers', component: 'DataProvidersPanel', file: 'components/settings/DataProvidersPanel.tsx' },
  { id: 'home-portfolio-health', component: 'HomePortfolioHealthWidget', file: 'components/dashboard/HomePortfolioHealthWidget.tsx' },
];

export const UNREACHABLE_CAPABILITY_LEDGER: readonly UnreachableCapabilityLedgerEntry[] = [
  {
    id: 'alerts-page-wrapper',
    component: 'AlertsPage',
    file: 'pages/AlertsPage.tsx',
    reason: 'Thin unused wrapper. Signal Center already hosts AlertsWorkspace on /signals; /alerts redirects there.',
    removeWhen: 'Owner deletes pages/AlertsPage.tsx after confirming Signal Center is the only alerts host (Refs #1058 Category C).',
  },
  {
    id: 'home-stock-workspace-composite',
    component: 'HomeStockWorkspace',
    file: 'components/watchlist/HomeStockWorkspace.tsx',
    reason: 'IA split this Home composite: Today/watchlist now live on HomeWatchlistGroupsSection; history/report details moved to Research Analysis.',
    removeWhen: 'Owner deletes HomeStockWorkspace or remounts it after an explicit product decision (Refs #1058, docs/stockpulse-ui-information-architecture.md).',
  },
];

const SKIP_PATH_SEGMENTS = new Set([
  '__tests__',
  'playground',
  'fixtures',
  'generated',
  'dev',
  'common',
]);

export function normalizeSrcRelativePath(inventoryKey: string): string {
  const segments: string[] = ['components', '__tests__'];
  for (const segment of inventoryKey.split('/')) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      segments.pop();
      continue;
    }
    segments.push(segment);
  }
  return segments.join('/');
}

export function isProductSurfacePath(srcPath: string): boolean {
  const segments = srcPath.split('/');
  if (segments.some((segment) => SKIP_PATH_SEGMENTS.has(segment))) return false;
  if (srcPath === 'pages/NotFoundPage.tsx') return false;
  return PRODUCT_SURFACE_SUFFIXES.some((suffix) => srcPath.endsWith(suffix));
}

export function isReexportOnlySource(source: string): boolean {
  const body = source
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('//'))
    .join('\n');
  return /^export\s+\{\s*default\s*\}\s+from\s+['"][^'"]+['"]\s*;?$/.test(body);
}

function stripSpecifier(raw: string): string {
  return raw.split(/[?#]/, 1)[0] ?? raw;
}

export function listRelativeValueImportSpecifiers(source: string): readonly string[] {
  const specifiers: string[] = [];
  for (const match of source.matchAll(/(?:^|\n)[ \t]*import\b/g)) {
    const at = match.index ?? 0;
    const windowText = source.slice(at, at + 1600).replace(/^\n/, '').trimStart();
    if (/^import\s+type\b/.test(windowText)) continue;
    const fromMatch = windowText.match(/^import\b[\s\S]*?\bfrom\s+['"](\.[^'"]+)['"]/);
    if (fromMatch?.[1]) {
      specifiers.push(stripSpecifier(fromMatch[1]));
      continue;
    }
    const sideEffect = windowText.match(/^import\s+['"](\.[^'"]+)['"]/);
    if (sideEffect?.[1] && /\.(?:ts|tsx)$/.test(sideEffect[1])) {
      specifiers.push(stripSpecifier(sideEffect[1]));
    }
  }
  for (const match of source.matchAll(/import\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
    if (match[1]) specifiers.push(stripSpecifier(match[1]));
  }
  for (const match of source.matchAll(/export\s+(?:\{[^}]*\}|\*)\s+from\s+['"](\.[^'"]+)['"]/g)) {
    if (match[1]) specifiers.push(stripSpecifier(match[1]));
  }
  return specifiers;
}

export function resolveRelativeModule(
  fromFile: string,
  specifier: string,
  knownFiles: ReadonlySet<string>,
): string | undefined {
  const fromDir = fromFile.split('/').slice(0, -1);
  const joined = [...fromDir, ...specifier.split('/')];
  const normalized: string[] = [];
  for (const segment of joined) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      normalized.pop();
      continue;
    }
    normalized.push(segment);
  }
  const base = normalized.join('/');
  const extensionless = base.replace(/\.(?:js|jsx|ts|tsx)$/, '');
  const candidates = /\.(?:ts|tsx)$/.test(base)
    ? [base]
    : [
        `${extensionless}.tsx`,
        `${extensionless}.ts`,
        `${extensionless}/index.tsx`,
        `${extensionless}/index.ts`,
      ];
  return candidates.find((candidate) => knownFiles.has(candidate));
}

export function parseAppRouteTable(
  appSource: string,
  routePaths: Record<string, string> = APP_ROUTE_PATHS,
): readonly AppRouteBinding[] {
  const bindings: AppRouteBinding[] = [];
  const lazyPattern = /const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\('(\.\/[^']+)'\)\)/g;
  for (const match of appSource.matchAll(lazyPattern)) {
    const ident = match[1];
    const spec = match[2];
    if (!ident || !spec || spec.includes('/playground/')) continue;
    const withoutPrefix = spec.replace(/^\.\//, '');
    const module = withoutPrefix.endsWith('.tsx') || withoutPrefix.endsWith('.ts')
      ? withoutPrefix
      : `${withoutPrefix}.tsx`;
    if (module.endsWith('NotFoundPage.tsx')) continue;
    const jsx = appSource.search(new RegExp(`<${ident}\\b`));
    if (jsx < 0) continue;
    const keys = [...appSource.slice(0, jsx).matchAll(/path:\s*APP_ROUTE_PATHS\.(\w+)/g)];
    const routeKey = keys.at(-1)?.[1];
    if (!routeKey) continue;
    const route = routePaths[routeKey];
    if (!route) continue;
    bindings.push({ ident, module, routeKey, route });
  }
  return bindings;
}

export function assertCapabilityHostMentions(
  source: string,
  component: string,
  id: string,
): void {
  const pattern = new RegExp(`\\b${component}\\b`);
  if (!pattern.test(source)) {
    throw new Error(`Capability ${id} lost its production host mention of ${component}`);
  }
}

export function buildValueImportConsumers(
  sources: Readonly<Record<string, string>>,
): Map<string, Set<string>> {
  const knownFiles = new Set(Object.keys(sources));
  const consumers = new Map<string, Set<string>>();
  for (const file of knownFiles) {
    consumers.set(file, new Set());
  }
  for (const [file, source] of Object.entries(sources)) {
    for (const specifier of listRelativeValueImportSpecifiers(source)) {
      const target = resolveRelativeModule(file, specifier, knownFiles);
      if (!target || target === file) continue;
      consumers.get(target)?.add(file);
    }
  }
  return consumers;
}

export function resolveProductionRoute(
  file: string,
  consumers: ReadonlyMap<string, ReadonlySet<string>>,
  routeByModule: ReadonlyMap<string, AppRouteBinding>,
): AppRouteBinding | undefined {
  const queued = [file];
  const seen = new Set<string>();
  while (queued.length > 0) {
    const current = queued.shift();
    if (!current || seen.has(current)) continue;
    seen.add(current);
    const routed = routeByModule.get(current);
    if (routed) return routed;
    for (const consumer of consumers.get(current) ?? []) {
      queued.push(consumer);
    }
  }
  return undefined;
}

export function listProductSurfaceFiles(
  srcPaths: readonly string[],
  sources: Readonly<Record<string, string>>,
): readonly string[] {
  return srcPaths.filter((srcPath) => {
    if (!isProductSurfacePath(srcPath)) return false;
    const source = sources[srcPath];
    if (source === undefined) return false;
    return !isReexportOnlySource(source);
  });
}

export function exportedComponentName(srcPath: string, source: string): string {
  const named = source.match(/export\s+(?:default\s+)?(?:const|function|class)\s+([A-Z][A-Za-z0-9_]*)/);
  if (named?.[1]) return named[1];
  const defaultExport = source.match(/export\s+default\s+([A-Z][A-Za-z0-9_]*)/);
  if (defaultExport?.[1]) return defaultExport[1];
  const stem = srcPath.split('/').at(-1) ?? srcPath;
  return stem.replace(/\.tsx$/, '');
}

export function buildReachabilityInventory(
  sources: Readonly<Record<string, string>>,
  appSource: string,
): {
  reachable: ReachabilityInventoryEntry[];
  unreachable: string[];
} {
  const routeBindings = parseAppRouteTable(appSource);
  const routeByModule = new Map(routeBindings.map((binding) => [binding.module, binding]));
  const consumers = buildValueImportConsumers(sources);
  const surfaceFiles = listProductSurfaceFiles(Object.keys(sources), sources);
  const reachable: ReachabilityInventoryEntry[] = [];
  const unreachable: string[] = [];
  for (const file of surfaceFiles) {
    const routed = resolveProductionRoute(file, consumers, routeByModule);
    if (!routed) {
      unreachable.push(file);
      continue;
    }
    reachable.push({
      file,
      component: exportedComponentName(file, sources[file] ?? ''),
      route: routed.route,
      routeKey: routed.routeKey,
    });
  }
  reachable.sort((left, right) => left.file.localeCompare(right.file));
  unreachable.sort();
  return { reachable, unreachable };
}
