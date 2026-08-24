// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { APP_ROUTE_PATHS } from './routes';

/**
 * Production reachability inventory for shipped Page/Panel/Workspace/Widget
 * surfaces (Refs #1058 / #1008). A capability is reachable when a named value
 * import or JSX/lazy host on an App.tsx route reaches its module. `export *`
 * barrels do not make every barrel importer a host of every re-exported
 * symbol. Unreachable leftovers are frozen in UNREACHABLE_CAPABILITY_LEDGER
 * (shrink-only).
 */

export type HostUsage = 'jsx' | 'lazy' | 'default-export';

export type NamedBoardCapability = {
  id: string;
  component: string;
  file: string;
  host: string;
  hostMention: string;
  hostUsage: HostUsage;
  routeKey: keyof typeof APP_ROUTE_PATHS;
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

export type RelativeValueImport = {
  specifier: string;
  kind: 'named' | 'default' | 'namespace' | 'dynamic';
  /** Export names requested from the specifier (`default` for default imports). */
  names: readonly string[];
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
 * Issue #1058 / #1008 named product capabilities. `host` is the production
 * file that must keep a JSX/lazy/default-export mention; `routeKey` is the
 * App route that host must remain on. Do not treat barrel BFS as the host.
 */
export const NAMED_BOARD_CAPABILITIES: readonly NamedBoardCapability[] = [
  {
    id: 'todays-focus',
    component: 'TodaysFocusPanel',
    file: 'components/home/TodaysFocusPanel.tsx',
    host: 'pages/HomePage.tsx',
    hostMention: 'TodaysFocusPanel',
    hostUsage: 'jsx',
    routeKey: 'home',
  },
  {
    id: 'watchlist-score-column',
    component: 'WatchlistScoreColumn',
    file: 'components/watchlist/WatchlistScoreColumn.tsx',
    host: 'components/watchlist/WatchlistGroupsPanel.tsx',
    hostMention: 'WatchlistScoreStatusCell',
    hostUsage: 'jsx',
    routeKey: 'home',
  },
  {
    id: 'dcf-sensitivity',
    component: 'DcfSensitivityPanel',
    file: 'components/valuation/DcfSensitivityPanel.tsx',
    host: 'pages/StockDetailsPage.tsx',
    hostMention: 'DcfSensitivityPanel',
    hostUsage: 'jsx',
    routeKey: 'stockDetails',
  },
  {
    id: 'report-export',
    component: 'ReportMarkdownPanel',
    file: 'components/report/ReportMarkdownPanel.tsx',
    host: 'pages/ResearchAnalysisWorkbenchPage.tsx',
    hostMention: 'ReportMarkdownDrawer',
    hostUsage: 'jsx',
    routeKey: 'researchAnalysis',
  },
  {
    id: 'report-version-compare',
    component: 'ReportVersionCompareView',
    file: 'components/report-version-compare/ReportVersionCompareView.tsx',
    host: 'pages/ReportVersionComparePage.tsx',
    hostMention: 'ReportVersionCompareView',
    hostUsage: 'jsx',
    routeKey: 'researchReportCompare',
  },
  {
    id: 'decision-signal-outcome-stats',
    component: 'DecisionSignalOutcomeStatsCard',
    file: 'components/decision-signals/DecisionSignalOutcomeStatsCard.tsx',
    host: 'pages/DecisionSignalsPage.tsx',
    hostMention: 'DecisionSignalReviewSection',
    hostUsage: 'jsx',
    routeKey: 'signals',
  },
  {
    id: 'event-calendar',
    component: 'EventCalendarWorkspace',
    file: 'components/event-calendar/EventCalendarWorkspace.tsx',
    host: 'pages/EventCalendarPage.tsx',
    hostMention: 'EventCalendarWorkspace',
    hostUsage: 'default-export',
    routeKey: 'eventCalendar',
  },
  {
    id: 'event-alerts',
    component: 'EventAlertsPanel',
    file: 'components/event-alerts/EventAlertsPanel.tsx',
    host: 'App.tsx',
    hostMention: 'EventAlertsPanel',
    hostUsage: 'lazy',
    routeKey: 'eventAlerts',
  },
  {
    id: 'zero-config-first-run',
    component: 'ZeroConfigFirstRunPanel',
    file: 'components/onboarding/ZeroConfigFirstRunPanel.tsx',
    host: 'components/onboarding/HomeOnboardingSection.tsx',
    hostMention: 'ZeroConfigFirstRunPanel',
    hostUsage: 'jsx',
    routeKey: 'home',
  },
  {
    id: 'portfolio-health',
    component: 'PortfolioHealthPanel',
    file: 'components/portfolio-insights/PortfolioHealthPanel.tsx',
    host: 'components/portfolio-insights/PortfolioInsightsWorkspace.tsx',
    hostMention: 'PortfolioHealthPanel',
    hostUsage: 'jsx',
    routeKey: 'portfolio',
  },
  {
    id: 'portfolio-stress',
    component: 'PortfolioStressPanel',
    file: 'components/portfolio-insights/PortfolioStressPanel.tsx',
    host: 'components/portfolio-insights/PortfolioInsightsWorkspace.tsx',
    hostMention: 'PortfolioStressPanel',
    hostUsage: 'jsx',
    routeKey: 'portfolio',
  },
  {
    id: 'portfolio-risk',
    component: 'PortfolioRiskMetricsPanel',
    file: 'components/portfolio-risk/PortfolioRiskMetricsPanel.tsx',
    host: 'components/portfolio/PortfolioWorkspace.tsx',
    hostMention: 'PortfolioRiskMetricsPanel',
    hostUsage: 'jsx',
    routeKey: 'portfolio',
  },
  {
    id: 'reasoning-trace-export',
    component: 'ReasoningTraceExportControls',
    file: 'components/report/ReasoningTraceExportControls.tsx',
    host: 'components/report/ReportMarkdownPanel.tsx',
    hostMention: 'ReasoningTraceExportControls',
    hostUsage: 'jsx',
    routeKey: 'researchMarket',
  },
  {
    id: 'kline-chart',
    component: 'KlineChart',
    file: 'components/charts/KlineChart.tsx',
    host: 'pages/StockDetailsPage.tsx',
    hostMention: 'KlineChart',
    hostUsage: 'jsx',
    routeKey: 'stockDetails',
  },
  {
    id: 'risk-heatmap',
    component: 'RiskHeatmap',
    file: 'components/charts/RiskHeatmap.tsx',
    host: 'components/portfolio/PortfolioWorkspace.tsx',
    hostMention: 'RiskHeatmap',
    hostUsage: 'jsx',
    routeKey: 'portfolio',
  },
  {
    id: 'loaded-extensions',
    component: 'LoadedExtensionsPanel',
    file: 'components/settings/LoadedExtensionsPanel.tsx',
    host: 'components/settings/sections/SystemSecuritySection.tsx',
    hostMention: 'LoadedExtensionsPanel',
    hostUsage: 'jsx',
    routeKey: 'settings',
  },
  {
    id: 'scheduled-tasks',
    component: 'ScheduledTasksPanel',
    file: 'components/settings/ScheduledTasksPanel.tsx',
    host: 'components/settings/sections/SystemSecuritySection.tsx',
    hostMention: 'ScheduledTasksPanel',
    hostUsage: 'jsx',
    routeKey: 'settings',
  },
  {
    id: 'data-providers',
    component: 'DataProvidersPanel',
    file: 'components/settings/DataProvidersPanel.tsx',
    host: 'components/settings/SettingsActiveConfigPanel.tsx',
    hostMention: 'DataProvidersPanel',
    hostUsage: 'jsx',
    routeKey: 'settings',
  },
  {
    id: 'home-portfolio-health',
    component: 'HomePortfolioHealthWidget',
    file: 'components/dashboard/HomePortfolioHealthWidget.tsx',
    host: 'pages/HomePage.tsx',
    hostMention: 'HomePortfolioHealthWidget',
    hostUsage: 'jsx',
    routeKey: 'home',
  },
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

/**
 * App.tsx product route table (non-playground). Fail if a page module is
 * rebound or dropped. Update this list only with the matching App.tsx change.
 */
export const APP_ROUTE_MODULE_SNAPSHOT: readonly { module: string; routeKey: string }[] = [
  { module: 'pages/HomePage.tsx', routeKey: 'home' },
  { module: 'pages/ResearchOverviewPage.tsx', routeKey: 'research' },
  { module: 'pages/ResearchAnalysisWorkbenchPage.tsx', routeKey: 'researchAnalysis' },
  { module: 'pages/MarketReviewPage.tsx', routeKey: 'researchMarket' },
  { module: 'pages/BacktestPage.tsx', routeKey: 'researchBacktest' },
  { module: 'pages/SkillOutcomesPage.tsx', routeKey: 'researchSkillOutcomes' },
  { module: 'pages/ReportVersionComparePage.tsx', routeKey: 'researchReportCompare' },
  { module: 'pages/SettingsPage.tsx', routeKey: 'settings' },
  { module: 'pages/LoginPage.tsx', routeKey: 'login' },
  { module: 'pages/ChatPage.tsx', routeKey: 'agent' },
  { module: 'pages/PortfolioPage.tsx', routeKey: 'portfolio' },
  { module: 'pages/PersonalPerformancePage.tsx', routeKey: 'portfolioPerformance' },
  { module: 'pages/EventCalendarPage.tsx', routeKey: 'eventCalendar' },
  { module: 'pages/DecisionSignalsPage.tsx', routeKey: 'signals' },
  { module: 'pages/ApprovalsPage.tsx', routeKey: 'approvals' },
  { module: 'pages/NotificationCenterPage.tsx', routeKey: 'notifications' },
  { module: 'pages/StockScreeningPage.tsx', routeKey: 'researchDiscover' },
  { module: 'pages/StockDetailsPage.tsx', routeKey: 'stockDetails' },
  { module: 'components/event-alerts/EventAlertsPanel.tsx', routeKey: 'eventAlerts' },
  { module: 'pages/FinancialCalculatorsPage.tsx', routeKey: 'calculators' },
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
  return /^export\s+\{\s*default\s*\}\s+from\s+['"][^'"]+['"]\s*;?$/.test(body)
    || /^export\s+\{[^}]+\}\s+from\s+['"][^'"]+['"]\s*;?$/.test(body);
}

function stripSpecifier(raw: string): string {
  return raw.split(/[?#]/, 1)[0] ?? raw;
}

function splitImportNames(inner: string): string[] {
  const names: string[] = [];
  for (const part of inner.split(',')) {
    const token = part.trim();
    if (!token || token === '{' || token === '}') continue;
    if (/^type\b/.test(token)) continue;
    const exported = token.replace(/^type\s+/, '').split(/\s+as\s+/i)[0]?.trim();
    if (exported && exported !== 'type') names.push(exported);
  }
  return names;
}

export function parseRelativeValueImports(source: string): readonly RelativeValueImport[] {
  const imports: RelativeValueImport[] = [];
  for (const match of source.matchAll(/(?:^|\n)[ \t]*import\b/g)) {
    const at = match.index ?? 0;
    const windowText = source.slice(at, at + 1600).replace(/^\n/, '').trimStart();
    if (/^import\s+type\b/.test(windowText)) continue;
    const fromMatch = windowText.match(/^import\b([\s\S]*?)\bfrom\s+['"](\.[^'"]+)['"]/);
    if (fromMatch?.[2]) {
      const clause = (fromMatch[1] ?? '').trim();
      const specifier = stripSpecifier(fromMatch[2]);
      if (clause.startsWith('*')) {
        imports.push({ specifier, kind: 'namespace', names: ['*'] });
        continue;
      }
      const named = clause.match(/\{([\s\S]*)\}/);
      const names = named?.[1] ? splitImportNames(named[1]) : [];
      const beforeBrace = clause.split('{')[0]?.replace(/,\s*$/, '').trim() ?? '';
      const hasDefault = beforeBrace.length > 0 && !beforeBrace.startsWith('{');
      if (names.length > 0) {
        imports.push({ specifier, kind: 'named', names });
      }
      if (hasDefault) {
        imports.push({ specifier, kind: 'default', names: ['default'] });
      }
      continue;
    }
    const sideEffect = windowText.match(/^import\s+['"](\.[^'"]+)['"]/);
    if (sideEffect?.[1] && /\.(?:ts|tsx)$/.test(sideEffect[1])) {
      imports.push({ specifier: stripSpecifier(sideEffect[1]), kind: 'namespace', names: ['*'] });
    }
  }
  for (const match of source.matchAll(/import\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
    if (match[1]) {
      imports.push({ specifier: stripSpecifier(match[1]), kind: 'dynamic', names: ['default'] });
    }
  }
  return imports;
}

export function listRelativeValueImportSpecifiers(source: string): readonly string[] {
  return [...new Set(parseRelativeValueImports(source).map((entry) => entry.specifier))];
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

function recordOrigin(map: Map<string, string>, name: string, origin: string): void {
  if (!map.has(name)) map.set(name, origin);
}

function collectLocalValueExportNames(source: string): string[] {
  const names: string[] = [];
  for (const match of source.matchAll(
    /^[ \t]*export\s+(?:async\s+)?(?:const|function|class)\s+([A-Za-z_$][\w$]*)/gm,
  )) {
    if (match[1]) names.push(match[1]);
  }
  if (/^[ \t]*export\s+default\b/m.test(source)) names.push('default');
  const defaultNamed = source.match(/^[ \t]*export\s+default\s+(?:function|class)\s+([A-Za-z_$][\w$]*)/m);
  if (defaultNamed?.[1]) names.push(defaultNamed[1]);
  const defaultIdent = source.match(/^[ \t]*export\s+default\s+([A-Za-z_$][\w$]*)\s*;?/m);
  if (defaultIdent?.[1] && defaultIdent[1] !== 'function' && defaultIdent[1] !== 'class') {
    names.push(defaultIdent[1]);
  }
  return names;
}

function parseExportFromClauses(source: string): Array<{ specifier: string; star: boolean; names: Array<{ exported: string; origin: string }> }> {
  const clauses: Array<{ specifier: string; star: boolean; names: Array<{ exported: string; origin: string }> }> = [];
  for (const match of source.matchAll(
    /^[ \t]*export\s+\*\s+from\s+['"](\.[^'"]+)['"]/gm,
  )) {
    if (match[1]) clauses.push({ specifier: stripSpecifier(match[1]), star: true, names: [] });
  }
  for (const match of source.matchAll(
    /^[ \t]*export\s+\{([\s\S]*?)\}\s+from\s+['"](\.[^'"]+)['"]/gm,
  )) {
    const inner = match[1];
    const specifier = match[2];
    if (!inner || !specifier) continue;
    const names: Array<{ exported: string; origin: string }> = [];
    for (const part of inner.split(',')) {
      const token = part.trim();
      if (!token || /^type\b/.test(token)) continue;
      const pieces = token.replace(/^type\s+/, '').split(/\s+as\s+/i);
      const originName = pieces[0]?.trim();
      const exportedName = (pieces[1] ?? pieces[0])?.trim();
      if (originName && exportedName) names.push({ exported: exportedName, origin: originName });
    }
    clauses.push({ specifier: stripSpecifier(specifier), star: false, names });
  }
  return clauses;
}

export function collectValueExportOrigins(
  file: string,
  sources: Readonly<Record<string, string>>,
  cache: Map<string, Map<string, string>> = new Map(),
  visiting: Set<string> = new Set(),
): Map<string, string> {
  const cached = cache.get(file);
  if (cached) return cached;
  if (visiting.has(file)) return new Map();
  visiting.add(file);
  const map = new Map<string, string>();
  const source = sources[file];
  if (source === undefined) {
    cache.set(file, map);
    visiting.delete(file);
    return map;
  }
  const knownFiles = new Set(Object.keys(sources));
  for (const name of collectLocalValueExportNames(source)) {
    recordOrigin(map, name, file);
  }
  for (const clause of parseExportFromClauses(source)) {
    const target = resolveRelativeModule(file, clause.specifier, knownFiles);
    if (!target) continue;
    const nested = collectValueExportOrigins(target, sources, cache, visiting);
    if (clause.star) {
      for (const [name, origin] of nested) {
        recordOrigin(map, name, origin);
      }
      continue;
    }
    for (const binding of clause.names) {
      const origin = nested.get(binding.origin) ?? target;
      recordOrigin(map, binding.exported, origin);
    }
  }
  cache.set(file, map);
  visiting.delete(file);
  return map;
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
  usage: HostUsage = 'jsx',
): void {
  const ok = usage === 'jsx'
    ? new RegExp(`<${component}\\b`).test(source)
    : usage === 'lazy'
      ? new RegExp(`import\\(\\s*['"][^'"\\n]*${component}['"]\\s*\\)`).test(source)
      : new RegExp(`export\\s+default\\s+${component}\\b`).test(source);
  if (!ok) {
    throw new Error(`Capability ${id} lost its production host ${usage} mention of ${component}`);
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
  const exportCache = new Map<string, Map<string, string>>();
  const addConsumer = (target: string, from: string) => {
    if (!target || target === from) return;
    consumers.get(target)?.add(from);
  };
  for (const [file, source] of Object.entries(sources)) {
    for (const imported of parseRelativeValueImports(source)) {
      const target = resolveRelativeModule(file, imported.specifier, knownFiles);
      if (!target) continue;
      const origins = collectValueExportOrigins(target, sources, exportCache);
      if (imported.kind === 'named') {
        for (const name of imported.names) {
          addConsumer(origins.get(name) ?? target, file);
        }
        continue;
      }
      if (imported.kind === 'default' || imported.kind === 'dynamic') {
        addConsumer(target, file);
        const defaultOrigin = origins.get('default');
        if (defaultOrigin) addConsumer(defaultOrigin, file);
        continue;
      }
      // Namespace / side-effect: consume the module file only, not every
      // export-star target (that is the barrel fail-open).
      addConsumer(target, file);
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
    for (const consumer of [...(consumers.get(current) ?? [])].sort()) {
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

export function formatReachableMapping(
  reachable: readonly ReachabilityInventoryEntry[],
): readonly string[] {
  return reachable.map((entry) => `${entry.file} ${entry.routeKey}`);
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
