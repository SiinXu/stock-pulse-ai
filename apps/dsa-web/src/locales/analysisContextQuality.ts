// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type {
  AnalysisContextPackBlockStatus,
  ReportLanguage,
} from '../types/analysis';

export type AnalysisContextQualityLevel = 'good' | 'usable' | 'limited' | 'poor';

export const ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS: Record<
  ReportLanguage,
  Record<AnalysisContextQualityLevel, string>
> = {
  zh: {
    good: '良好',
    usable: '可用',
    limited: '受限',
    poor: '较差',
  },
  en: {
    good: 'Good',
    usable: 'Usable',
    limited: 'Limited',
    poor: 'Poor',
  },
  ko: {
    good: '양호',
    usable: '사용 가능',
    limited: '제한적',
    poor: '미흡',
  },
};

export const ANALYSIS_CONTEXT_STATUS_LABELS: Record<
  ReportLanguage,
  Record<AnalysisContextPackBlockStatus, string>
> = {
  zh: {
    available: '可用',
    missing: '缺失',
    not_supported: '不支持',
    fallback: '降级',
    stale: '过期',
    estimated: '估算',
    partial: '部分可用',
    fetch_failed: '抓取失败',
  },
  en: {
    available: 'Available',
    missing: 'Missing',
    not_supported: 'Not supported',
    fallback: 'Fallback',
    stale: 'Stale',
    estimated: 'Estimated',
    partial: 'Partial',
    fetch_failed: 'Fetch failed',
  },
  ko: {
    available: '사용 가능',
    missing: '누락',
    not_supported: '미지원',
    fallback: '강등',
    stale: '만료',
    estimated: '추정',
    partial: '부분 사용',
    fetch_failed: '수집 실패',
  },
};

export const ANALYSIS_CONTEXT_BLOCK_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    quote: '行情',
    daily_bars: '日线',
    technical: '技术',
    news: '新闻',
    fundamentals: '基本面',
    chip: '筹码',
  },
  en: {
    quote: 'quote',
    daily_bars: 'daily bars',
    technical: 'technical',
    news: 'news',
    fundamentals: 'fundamentals',
    chip: 'chip',
  },
  ko: {
    quote: '시세',
    daily_bars: '일봉',
    technical: '기술',
    news: '뉴스',
    fundamentals: '펀더멘털',
    chip: '매물대',
  },
};
