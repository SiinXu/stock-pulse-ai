// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  documentTitle: '选股发现 - StockPulse',
  pageTitle: '选股发现',
  pageDescription: '在同一页面使用有界 AI 候选发现，或可选的 AlphaSift 策略选股；结果仅供研究，不是交易指令。',
  discoveryStatusReady: 'AI 发现可用（有界）',
  modeStrategy: '策略选股',
  modeDiscovery: 'AI 发现',
  discoveryTitle: 'AI 候选发现（有界）',
  discoveryDescription: '用自然语言或条件在自选/持仓/指数分页宇宙中发现候选。行情经 data_provider 限次获取，禁止无界全市场扫描。',
  discoveryDisclaimer: '仅供研究筛选，不构成投资建议或交易指令。',
  discoveryQuery: '自然语言 / 条件',
  discoveryQueryPlaceholder: '例如：银行 涨幅>2 成交额>1亿',
  discoveryUniverse: '宇宙',
  discoveryUniverseWatchlist: '自选',
  discoveryUniversePortfolio: '持仓',
  discoveryUniverseIndex: '符号指数分页',
  discoveryPage: '页码',
  discoveryPageSize: '每页数量',
  discoveryMaxResults: '返回上限',
  discoveryProviderBudget: '行情调用预算',
  discoveryRun: '运行发现',
  discoveryRunning: '发现运行中…',
  discoverySubmitting: '正在提交发现任务…',
  discoveryCancel: '取消',
  discoveryCancelRequested: '已请求取消',
  discoveryCancelFailed: '取消失败',
  discoveryFailed: '候选发现失败',
  discoveryNoHits: '当前宇宙与条件没有命中候选。',
  discoveryProgress: '进度 {progress}% · {message}',
  discoveryCostSummary: '成本：行情 {provider}/{maxProvider} · 候选 {candidates}',
  discoveryUniverseSummary: '宇宙 {source} · 解析 {resolved} · 评估 {evaluated}',
  discoveryAddWatchlist: '加入自选',
  discoveryWatchlistAdded: '已加入自选：{code}',
  discoveryWatchlistFailed: '加入自选失败',
} as const;

const en: Record<keyof typeof zh, string> = {
  documentTitle: 'Discover - StockPulse',
  pageTitle: 'Discover',
  pageDescription: 'Use bounded AI candidate discovery on this page, or optional AlphaSift strategy screening. Research only — not trade instructions.',
  discoveryStatusReady: 'AI discovery ready (bounded)',
  modeStrategy: 'Strategy screen',
  modeDiscovery: 'AI discovery',
  discoveryTitle: 'AI candidate discovery (bounded)',
  discoveryDescription: 'Discover candidates from watchlist, portfolio, or paginated index universes with natural language or criteria. Quotes use data_provider call budgets — no unbounded full-market scan.',
  discoveryDisclaimer: 'Research screening only. Not investment advice or trade instructions.',
  discoveryQuery: 'Natural language / criteria',
  discoveryQueryPlaceholder: 'e.g. banks change > 2 amount > 100m',
  discoveryUniverse: 'Universe',
  discoveryUniverseWatchlist: 'Watchlist',
  discoveryUniversePortfolio: 'Portfolio',
  discoveryUniverseIndex: 'Symbol-index page',
  discoveryPage: 'Page',
  discoveryPageSize: 'Page size',
  discoveryMaxResults: 'Max results',
  discoveryProviderBudget: 'Provider call budget',
  discoveryRun: 'Run discovery',
  discoveryRunning: 'Discovery running…',
  discoverySubmitting: 'Submitting discovery task…',
  discoveryCancel: 'Cancel',
  discoveryCancelRequested: 'Cancel requested',
  discoveryCancelFailed: 'Could not cancel discovery',
  discoveryFailed: 'Candidate discovery failed',
  discoveryNoHits: 'No candidates matched this universe and criteria.',
  discoveryProgress: 'Progress {progress}% · {message}',
  discoveryCostSummary: 'Cost: quotes {provider}/{maxProvider} · candidates {candidates}',
  discoveryUniverseSummary: 'Universe {source} · resolved {resolved} · evaluated {evaluated}',
  discoveryAddWatchlist: 'Add to watchlist',
  discoveryWatchlistAdded: 'Added to watchlist: {code}',
  discoveryWatchlistFailed: 'Could not add to watchlist',
};

export type CandidateDiscoveryText = Record<keyof typeof zh, string>;
type AdditionalLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

const TRANSLATION_LOADERS = {
  de: () => import('./candidateDiscoveryTranslations/de'),
  es: () => import('./candidateDiscoveryTranslations/es'),
  fr: () => import('./candidateDiscoveryTranslations/fr'),
  id: () => import('./candidateDiscoveryTranslations/id'),
  ja: () => import('./candidateDiscoveryTranslations/ja'),
  ko: () => import('./candidateDiscoveryTranslations/ko'),
  ms: () => import('./candidateDiscoveryTranslations/ms'),
  'zh-TW': () => import('./candidateDiscoveryTranslations/zh-TW'),
} satisfies Record<AdditionalLanguage, () => Promise<{ default: CandidateDiscoveryText }>>;

const translationCache = new Map<AdditionalLanguage, CandidateDiscoveryText>();

export function getCandidateDiscoveryText(language: UiLanguage): CandidateDiscoveryText | null {
  if (language === 'zh') return zh;
  if (language === 'en') return en;
  return translationCache.get(language) ?? null;
}

export async function loadCandidateDiscoveryText(language: UiLanguage): Promise<CandidateDiscoveryText> {
  if (language === 'zh') return zh;
  if (language === 'en') return en;
  const cached = translationCache.get(language);
  if (cached) return cached;
  const translated = (await TRANSLATION_LOADERS[language]()).default;
  translationCache.set(language, translated);
  return translated;
}

export const SOURCE_CANDIDATE_DISCOVERY_TEXT = { zh, en } as const;
