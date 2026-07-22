// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
//
// Rich, larger-scale fixtures for the dev-only app API mock. These are imported
// only by the dev mock switch (behind import.meta.env.DEV), so they are tree-
// shaken out of production builds and never ship. Base single-item templates are
// reused from the playground fixtures to avoid duplicating field contracts.
import {
  FIXTURE_TIMESTAMP,
  fixtureAlertRules,
  fixtureAlertTriggers,
  fixtureDecisionSignal,
  fixtureDecisionSignals,
  fixtureHistoryItems,
  fixtureProviders,
  fixtureTasks,
} from '../../playground/fixtures';
import type { DecisionAction, HistoryItem, StockBarItem, TaskInfo } from '../../types/analysis';
import type { AlertRuleItem, AlertSeverity, AlertTriggerItem } from '../../types/alerts';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';

const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

const makeHistoryItem = (
  id: number,
  stockCode: string,
  stockName: string,
  action: DecisionAction,
  sentimentScore: number,
  currentPrice: number,
  changePct: number,
  reportType: HistoryItem['reportType'] = 'detailed',
): HistoryItem => ({
  id,
  queryId: `fixture-query-${id}`,
  stockCode,
  stockName,
  reportType,
  trendPrediction: changePct >= 0 ? 'Positive bias' : 'Cooling momentum',
  analysisSummary: `${stockName} ${action} setup under review`,
  sentimentScore,
  operationAdvice: titleCase(action),
  action,
  actionLabel: titleCase(action),
  currentPrice,
  changePct,
  volumeRatio: Number((1 + (id % 5) * 0.12).toFixed(2)),
  turnoverRate: Number((0.2 + (id % 7) * 0.05).toFixed(2)),
  modelUsed: 'fixture-route',
  createdAt: FIXTURE_TIMESTAMP,
});

export const richHistoryItems: HistoryItem[] = [
  ...fixtureHistoryItems,
  makeHistoryItem(103, '300750', 'CATL', 'buy', 78, 198.4, 3.1),
  makeHistoryItem(104, '000858', 'Wuliangye', 'watch', 63, 142.7, 0.8),
  makeHistoryItem(105, '601899', 'Zijin Mining', 'add', 71, 18.9, 1.9),
  makeHistoryItem(106, '002594', 'BYD', 'hold', 58, 245.3, -0.6, 'brief'),
  makeHistoryItem(107, '600036', 'China Merchants Bank', 'watch', 60, 38.1, 0.4),
  makeHistoryItem(108, '00700', 'Tencent', 'buy', 74, 402.6, 2.2),
  makeHistoryItem(109, '09988', 'Alibaba', 'hold', 55, 78.4, -1.1, 'brief'),
  makeHistoryItem(110, '03690', 'Meituan', 'reduce', 44, 118.2, -2.4),
  makeHistoryItem(111, 'NVDA', 'NVIDIA', 'buy', 82, 138.5, 3.6),
  makeHistoryItem(112, 'MSFT', 'Microsoft', 'hold', 61, 428.9, 0.3),
  makeHistoryItem(113, 'TSLA', 'Tesla', 'reduce', 47, 246.1, -2.8),
  makeHistoryItem(114, 'AMZN', 'Amazon', 'watch', 64, 201.7, 0.9, 'brief'),
  makeHistoryItem(115, 'GOOGL', 'Alphabet', 'add', 69, 176.3, 1.4),
  makeHistoryItem(116, '601398', 'ICBC', 'hold', 52, 6.4, 0.2),
  makeHistoryItem(117, '000001', 'Ping An Bank', 'watch', 57, 11.8, -0.3),
  makeHistoryItem(118, '600030', 'CITIC Securities', 'add', 66, 26.5, 1.1),
  makeHistoryItem(119, '300059', 'East Money', 'buy', 73, 17.2, 2.9, 'brief'),
  makeHistoryItem(120, '002415', 'Hikvision', 'hold', 59, 31.6, -0.4),
  makeHistoryItem(121, 'META', 'Meta Platforms', 'buy', 70, 612.4, 1.7),
  makeHistoryItem(122, '00939', 'China Construction Bank', 'hold', 53, 6.9, 0.1),
  makeHistoryItem(123, '601288', 'Agricultural Bank', 'watch', 56, 5.1, 0.5),
  makeHistoryItem(124, 'AMD', 'Advanced Micro Devices', 'reduce', 48, 122.8, -1.9, 'brief'),
];

export const richStockBarItems: StockBarItem[] = richHistoryItems.map((item, index) => ({
  id: item.id,
  stockCode: item.stockCode,
  stockName: item.stockName,
  reportType: item.reportType,
  sentimentScore: item.sentimentScore,
  operationAdvice: item.operationAdvice,
  action: item.action,
  actionLabel: item.actionLabel,
  analysisCount: (index % 6) + 2,
  lastAnalysisTime: item.createdAt,
  modelUsed: item.modelUsed,
}));

const makeDecisionSignal = (
  id: number,
  stockCode: string,
  stockName: string,
  market: DecisionSignalItem['market'],
  action: DecisionAction,
  score: number,
  confidence: number,
  status: DecisionSignalItem['status'],
  createdAt: string,
): DecisionSignalItem => ({
  ...fixtureDecisionSignal,
  id,
  stockCode,
  stockName,
  market,
  action,
  actionLabel: titleCase(action),
  score,
  confidence,
  status,
  createdAt,
  updatedAt: createdAt,
});

export const richDecisionSignals: DecisionSignalItem[] = [
  ...fixtureDecisionSignals,
  makeDecisionSignal(304, '300750', 'CATL', 'cn', 'buy', 78, 0.79, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(305, '000858', 'Wuliangye', 'cn', 'watch', 63, 0.66, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(306, '002594', 'BYD', 'cn', 'hold', 58, 0.6, 'active', '2026-07-19T15:30:00Z'),
  makeDecisionSignal(307, 'NVDA', 'NVIDIA', 'us', 'buy', 82, 0.83, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(308, 'MSFT', 'Microsoft', 'us', 'hold', 61, 0.62, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(309, 'TSLA', 'Tesla', 'us', 'reduce', 47, 0.55, 'expired', '2026-07-18T15:30:00Z'),
  makeDecisionSignal(310, '09988', 'Alibaba', 'hk', 'watch', 56, 0.59, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(311, '03690', 'Meituan', 'hk', 'reduce', 44, 0.53, 'expired', '2026-07-17T15:30:00Z'),
  makeDecisionSignal(312, '601899', 'Zijin Mining', 'cn', 'add', 71, 0.72, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(313, 'GOOGL', 'Alphabet', 'us', 'buy', 69, 0.7, 'active', FIXTURE_TIMESTAMP),
  makeDecisionSignal(314, '600036', 'China Merchants Bank', 'cn', 'hold', 60, 0.61, 'active', '2026-07-19T15:30:00Z'),
  makeDecisionSignal(315, 'AMD', 'Advanced Micro Devices', 'us', 'reduce', 48, 0.54, 'expired', '2026-07-16T15:30:00Z'),
];

const makeAlertRule = (
  id: number,
  name: string,
  target: string,
  severity: AlertSeverity,
  enabled: boolean,
  price: number,
): AlertRuleItem => ({
  id,
  name,
  targetScope: 'single_symbol',
  target,
  alertType: 'price_cross',
  parameters: { direction: 'above', price },
  severity,
  enabled,
  source: 'playground',
  cooldownActive: false,
  createdAt: FIXTURE_TIMESTAMP,
  updatedAt: FIXTURE_TIMESTAMP,
});

export const richAlertRules: AlertRuleItem[] = [
  ...fixtureAlertRules,
  makeAlertRule(503, 'CATL breakout', '300750', 'info', true, 210),
  makeAlertRule(504, 'NVIDIA momentum', 'NVDA', 'warning', true, 145),
  makeAlertRule(505, 'BYD support break', '002594', 'critical', true, 235),
  makeAlertRule(506, 'Tencent target', '00700', 'info', false, 420),
  makeAlertRule(507, 'Tesla stop watch', 'TSLA', 'warning', true, 250),
  {
    id: 508,
    name: 'US market risk light',
    targetScope: 'market',
    target: 'us',
    alertType: 'market_light_status',
    parameters: { statuses: ['red'] },
    severity: 'critical',
    enabled: true,
    source: 'playground',
    cooldownActive: false,
    createdAt: FIXTURE_TIMESTAMP,
    updatedAt: FIXTURE_TIMESTAMP,
  },
];

const makeAlertTrigger = (
  id: number,
  ruleId: number,
  target: string,
  observedValue: number,
  threshold: number,
  status: AlertTriggerItem['status'],
  triggeredAt: string = FIXTURE_TIMESTAMP,
): AlertTriggerItem => ({
  id,
  ruleId,
  target,
  observedValue,
  threshold,
  reason: status === 'triggered'
    ? 'Price crossed the configured threshold.'
    : 'Condition was not met at evaluation time.',
  dataSource: 'fixture_quote',
  dataTimestamp: triggeredAt,
  triggeredAt,
  status,
  diagnostics: `fixture-trigger-${id}`,
});

export const richAlertTriggers: AlertTriggerItem[] = [
  ...fixtureAlertTriggers,
  makeAlertTrigger(603, 503, '300750', 211.4, 210, 'triggered'),
  makeAlertTrigger(604, 504, 'NVDA', 146.2, 145, 'triggered'),
  makeAlertTrigger(605, 505, '002594', 233.1, 235, 'skipped'),
  makeAlertTrigger(606, 507, 'TSLA', 249.0, 250, 'skipped'),
  makeAlertTrigger(607, 501, '600519', 1503.6, 1500, 'triggered', '2026-07-19T09:35:00Z'),
  makeAlertTrigger(608, 503, '300750', 212.9, 210, 'triggered', '2026-07-19T10:05:00Z'),
  makeAlertTrigger(609, 504, 'NVDA', 147.8, 145, 'triggered', '2026-07-19T13:45:00Z'),
  makeAlertTrigger(610, 505, '002594', 236.4, 235, 'triggered', '2026-07-18T14:20:00Z'),
  makeAlertTrigger(611, 507, 'TSLA', 251.2, 250, 'triggered', '2026-07-18T15:00:00Z'),
  makeAlertTrigger(612, 501, '600519', 1498.2, 1500, 'skipped', '2026-07-18T09:40:00Z'),
  makeAlertTrigger(613, 503, '300750', 208.5, 210, 'skipped', '2026-07-17T11:10:00Z'),
  makeAlertTrigger(614, 504, 'NVDA', 149.1, 145, 'triggered', '2026-07-17T13:30:00Z'),
  makeAlertTrigger(615, 505, '002594', 240.7, 235, 'triggered', '2026-07-16T14:50:00Z'),
  makeAlertTrigger(616, 507, 'TSLA', 253.9, 250, 'triggered', '2026-07-16T15:10:00Z'),
];

const makeTask = (
  n: number,
  stockCode: string,
  stockName: string,
  status: TaskInfo['status'],
  progress: number,
  message: string,
): TaskInfo => ({
  taskId: `fixture-task-${n}`,
  traceId: `fixture-trace-${n}`,
  stockCode,
  stockName,
  status,
  progress,
  message,
  reportType: 'detailed',
  createdAt: FIXTURE_TIMESTAMP,
  ...(status === 'completed' ? { completedAt: FIXTURE_TIMESTAMP } : {}),
});

export const richTasks: TaskInfo[] = [
  ...fixtureTasks,
  makeTask(103, '300750', 'CATL', 'processing', 38, 'Fetching market data'),
  makeTask(104, 'NVDA', 'NVIDIA', 'pending', 0, 'Queued for analysis'),
  makeTask(105, '00700', 'Tencent', 'completed', 100, 'Analysis completed'),
  makeTask(106, 'TSLA', 'Tesla', 'failed', 72, 'Model provider timed out'),
  makeTask(107, '002594', 'BYD', 'cancelled', 21, 'Cancelled by user'),
  makeTask(108, '601899', 'Zijin Mining', 'interrupted', 55, 'Run interrupted mid-pipeline'),
];

const makeProvider = (
  id: string,
  label: string,
  protocol: string,
  defaultBaseUrl: string,
  opts: Partial<LlmProviderCatalogEntry> = {},
): LlmProviderCatalogEntry => ({
  id,
  label,
  labelZh: label,
  labelEn: label,
  protocol,
  defaultBaseUrl,
  credentialUrl: null,
  consoleUrl: null,
  modelsUrl: null,
  docsUrl: null,
  capabilities: ['chat', 'json'],
  requiresApiKey: true,
  requiresBaseUrl: false,
  supportsDiscovery: true,
  isLocal: false,
  isCustom: false,
  ...opts,
});

export const richProviders: LlmProviderCatalogEntry[] = [
  ...fixtureProviders,
  makeProvider('fixture-anthropic', 'Fixture Anthropic', 'anthropic', 'https://api.anthropic.example.invalid', { capabilities: ['chat', 'tools', 'vision'] }),
  makeProvider('fixture-gemini', 'Fixture Gemini', 'gemini', 'https://gemini.example.invalid', { capabilities: ['chat', 'json', 'vision'] }),
  makeProvider('fixture-local', 'Fixture Local (Ollama)', 'ollama', 'http://127.0.0.1:11434', { requiresApiKey: false, isLocal: true }),
];

export type IntelligenceSourceFixture = {
  id: number;
  name: string;
  sourceType: string;
  url: string;
  enabled: boolean;
  scopeType: string;
  scopeValue: string | null;
  market: string;
  description: string | null;
  lastStatus: string | null;
  lastError: string | null;
  lastFetchedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

const makeIntelligenceSource = (
  id: number,
  name: string,
  sourceType: string,
  url: string,
  market: string,
  lastStatus: string | null,
  lastError: string | null = null,
  enabled = true,
): IntelligenceSourceFixture => ({
  id,
  name,
  sourceType,
  url,
  enabled,
  scopeType: 'market',
  scopeValue: null,
  market,
  description: `${name} deterministic dev source.`,
  lastStatus,
  lastError,
  lastFetchedAt: lastStatus === 'success' ? FIXTURE_TIMESTAMP : null,
  createdAt: FIXTURE_TIMESTAMP,
  updatedAt: FIXTURE_TIMESTAMP,
});

export const richIntelligenceSources: IntelligenceSourceFixture[] = [
  makeIntelligenceSource(701, 'Market fixture feed', 'rss', 'https://example.invalid/market-feed.xml', 'cn', 'success'),
  makeIntelligenceSource(702, 'A-share newsflash', 'rss', 'https://example.invalid/cn-flash.xml', 'cn', 'success'),
  makeIntelligenceSource(703, 'HK exchange filings', 'rss', 'https://example.invalid/hk-filings.xml', 'hk', 'success'),
  makeIntelligenceSource(704, 'US macro wire', 'rss', 'https://example.invalid/us-macro.xml', 'us', 'error', 'Fixture fetch timeout'),
  makeIntelligenceSource(705, 'Sector research digest', 'api', 'https://example.invalid/sector-digest', 'cn', 'success', null, false),
  makeIntelligenceSource(706, 'Global commodities feed', 'rss', 'https://example.invalid/commodities.xml', 'us', null),
];

const makeIntelligenceItem = (
  id: number,
  sourceId: number,
  sourceName: string,
  title: string,
  summary: string,
  market: string,
  publishedAt: string = FIXTURE_TIMESTAMP,
) => ({
  id,
  sourceId,
  sourceName,
  sourceType: 'rss',
  title,
  summary,
  url: `https://example.invalid/intelligence/${id}`,
  source: 'dev-mock',
  publishedAt,
  fetchedAt: FIXTURE_TIMESTAMP,
  scopeType: 'market',
  scopeValue: null,
  market,
});

export const richIntelligenceItems = [
  makeIntelligenceItem(801, 701, 'Market fixture feed', 'Breadth expands as turnover climbs', 'Advancers outpaced decliners across the session.', 'cn'),
  makeIntelligenceItem(802, 702, 'A-share newsflash', 'Consumer names lead the rebound', 'Premium liquor and beverages extended gains.', 'cn'),
  makeIntelligenceItem(803, 702, 'A-share newsflash', 'Regulator signals steady liquidity', 'Policy tone stays supportive into quarter-end.', 'cn', '2026-07-19T15:30:00Z'),
  makeIntelligenceItem(804, 703, 'HK exchange filings', 'Tencent buyback continues', 'Daily repurchase cadence held through the week.', 'hk'),
  makeIntelligenceItem(805, 703, 'HK exchange filings', 'Meituan guidance under review', 'Delivery margin commentary drew scrutiny.', 'hk', '2026-07-18T15:30:00Z'),
  makeIntelligenceItem(806, 704, 'US macro wire', 'Rate path repricing accelerates', 'Front-end yields eased after softer prints.', 'us'),
  makeIntelligenceItem(807, 704, 'US macro wire', 'Semis lead risk appetite', 'AI capex narrative kept momentum intact.', 'us', '2026-07-19T13:00:00Z'),
  makeIntelligenceItem(808, 705, 'Sector research digest', 'Battery supply chain restocks', 'Cathode utilization ticked higher month over month.', 'cn'),
  makeIntelligenceItem(809, 706, 'Global commodities feed', 'Gold holds near range highs', 'Real yields and haven demand stayed balanced.', 'us', '2026-07-17T15:30:00Z'),
];

export const richAlertNotifications = [
  { id: 901, triggerId: 601, channel: 'email', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 42, diagnostics: 'fixture-notify-901', createdAt: FIXTURE_TIMESTAMP },
  { id: 902, triggerId: 603, channel: 'feishu', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 58, diagnostics: 'fixture-notify-902', createdAt: FIXTURE_TIMESTAMP },
  { id: 903, triggerId: 604, channel: 'webhook', attempt: 2, success: false, errorCode: 'timeout', retryable: true, latencyMs: 3000, diagnostics: 'fixture-notify-903', createdAt: '2026-07-19T13:46:00Z' },
  { id: 904, triggerId: 607, channel: 'email', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 39, diagnostics: 'fixture-notify-904', createdAt: '2026-07-19T09:36:00Z' },
  { id: 905, triggerId: 609, channel: 'feishu', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 61, diagnostics: 'fixture-notify-905', createdAt: '2026-07-19T13:45:30Z' },
  { id: 906, triggerId: 611, channel: 'sms', attempt: 3, success: false, errorCode: 'rate_limited', retryable: true, latencyMs: 1200, diagnostics: 'fixture-notify-906', createdAt: '2026-07-18T15:01:00Z' },
  { id: 907, triggerId: 614, channel: 'email', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 44, diagnostics: 'fixture-notify-907', createdAt: '2026-07-17T13:31:00Z' },
  { id: 908, triggerId: 615, channel: 'webhook', attempt: 1, success: true, errorCode: null, retryable: false, latencyMs: 72, diagnostics: 'fixture-notify-908', createdAt: '2026-07-16T14:51:00Z' },
];
