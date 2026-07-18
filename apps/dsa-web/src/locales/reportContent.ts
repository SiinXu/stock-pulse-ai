// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type {
  AnalysisContextPackBlockStatus,
  MarketStructureStatus,
  MarketStructureStockRole,
  MarketStructureThemePhase,
  ReportLanguage,
} from '../types/analysis';

type QualityLevel = 'good' | 'usable' | 'limited' | 'poor';

type AnalysisContextContent = {
  eyebrow: string;
  title: string;
  counts: string;
  source: string;
  warnings: string;
  missingReasons: string;
  inputScope: string;
  evidenceScope: string;
  qualityScore: string;
  limitations: string;
  newsResultCount: string;
  triggerSource: string;
  qualityLevel: Record<QualityLevel, string>;
  status: Record<AnalysisContextPackBlockStatus, string>;
  blockLabels: Record<string, string>;
  missingReasonLabels: Record<string, string>;
};

export const ANALYSIS_CONTEXT_CONTENT_TEXT: Record<ReportLanguage, AnalysisContextContent> = {
  zh: {
    eyebrow: '数据上下文',
    title: '输入数据块',
    counts: '状态计数',
    source: '来源',
    warnings: '告警',
    missingReasons: '缺失原因',
    inputScope: '本次分析输入',
    evidenceScope: '仅代表进入本次 LLM 的输入，不等同于数据源运行成功',
    qualityScore: '质量分',
    limitations: '数据限制',
    newsResultCount: '新闻结果数',
    triggerSource: '触发来源',
    qualityLevel: {
      good: '良好',
      usable: '可用',
      limited: '受限',
      poor: '较差',
    },
    status: {
      available: '可用',
      missing: '缺失',
      not_supported: '不支持',
      fallback: '降级',
      stale: '过期',
      estimated: '估算',
      partial: '部分可用',
      fetch_failed: '抓取失败',
    },
    blockLabels: {
      quote: '行情',
      daily_bars: '日线',
      technical: '技术',
      news: '新闻',
      fundamentals: '基本面',
      chip: '筹码',
    },
    missingReasonLabels: {
      daily_bars_missing: '未进入分析输入',
      news_context_missing: '未进入分析输入',
      realtime_quote_missing: '未进入分析输入',
      trend_result_missing: '未进入分析输入',
      fundamental_context_missing: '未进入分析输入',
      chip_distribution_missing: '未进入分析输入',
      today_missing: '今日数据未进入分析输入',
      yesterday_missing: '昨日数据未进入分析输入',
    },
  },
  en: {
    eyebrow: 'DATA CONTEXT',
    title: 'Input Blocks',
    counts: 'Status Counts',
    source: 'Source',
    warnings: 'Warnings',
    missingReasons: 'Missing Reasons',
    inputScope: 'Analysis Input',
    evidenceScope: 'Shows inputs included in this LLM run, not provider run success',
    qualityScore: 'Quality',
    limitations: 'Data Limitations',
    newsResultCount: 'News Results',
    triggerSource: 'Trigger',
    qualityLevel: {
      good: 'Good',
      usable: 'Usable',
      limited: 'Limited',
      poor: 'Poor',
    },
    status: {
      available: 'Available',
      missing: 'Missing',
      not_supported: 'Not supported',
      fallback: 'Fallback',
      stale: 'Stale',
      estimated: 'Estimated',
      partial: 'Partial',
      fetch_failed: 'Fetch failed',
    },
    blockLabels: {
      quote: 'quote',
      daily_bars: 'daily bars',
      technical: 'technical',
      news: 'news',
      fundamentals: 'fundamentals',
      chip: 'chip',
    },
    missingReasonLabels: {
      daily_bars_missing: 'Not included in analysis input',
      news_context_missing: 'Not included in analysis input',
      realtime_quote_missing: 'Not included in analysis input',
      trend_result_missing: 'Not included in analysis input',
      fundamental_context_missing: 'Not included in analysis input',
      chip_distribution_missing: 'Not included in analysis input',
      today_missing: 'Today data not included in analysis input',
      yesterday_missing: 'Yesterday data not included in analysis input',
    },
  },
  ko: {
    eyebrow: '정보 컨텍스트',
    title: '입력 데이터 블록',
    counts: '상태 카운트',
    source: '출처',
    warnings: '경고',
    missingReasons: '누락 사유',
    inputScope: '이번 분석 입력',
    evidenceScope: '이번 LLM 입력에 포함된 항목만 표시하며, 데이터 소스 실행 성공과는 다릅니다',
    qualityScore: '품질 점수',
    limitations: '데이터 한계',
    newsResultCount: '뉴스 결과 수',
    triggerSource: '트리거',
    qualityLevel: {
      good: '양호',
      usable: '사용 가능',
      limited: '제한적',
      poor: '미흡',
    },
    status: {
      available: '사용 가능',
      missing: '누락',
      not_supported: '미지원',
      fallback: '강등',
      stale: '만료',
      estimated: '추정',
      partial: '부분 사용',
      fetch_failed: '수집 실패',
    },
    blockLabels: {
      quote: '시세',
      daily_bars: '일봉',
      technical: '기술',
      news: '뉴스',
      fundamentals: '펀더멘털',
      chip: '매물대',
    },
    missingReasonLabels: {
      daily_bars_missing: '분석 입력에 포함되지 않음',
      news_context_missing: '분석 입력에 포함되지 않음',
      realtime_quote_missing: '분석 입력에 포함되지 않음',
      trend_result_missing: '분석 입력에 포함되지 않음',
      fundamental_context_missing: '분석 입력에 포함되지 않음',
      chip_distribution_missing: '분석 입력에 포함되지 않음',
      today_missing: '당일 데이터가 분석 입력에 포함되지 않음',
      yesterday_missing: '전일 데이터가 분석 입력에 포함되지 않음',
    },
  },
};

type MarketReviewContent = {
  eyebrow: string;
  defaultTitle: string;
  fullReview: string;
  overview: string;
  defaultSectionTitle: string;
  reviewSummary: string;
  noReviewSummary: string;
  noSentimentScore: string;
  rotationAndFunds: string;
  noRotationView: string;
  riskAndWatch: string;
  noRiskWatch: string;
  structuredMarketData: string;
  noBreadthData: string;
  advancers: string;
  decliners: string;
  limitUpDown: string;
  turnover: string;
  index: string;
  last: string;
  change: string;
  highLow: string;
  industryBoards: string;
  conceptBoards: string;
  leading: string;
  lagging: string;
};

export const MARKET_REVIEW_CONTENT_TEXT: Record<ReportLanguage, MarketReviewContent> = {
  zh: {
    eyebrow: '大盘复盘',
    defaultTitle: '大盘复盘',
    fullReview: '复盘正文',
    overview: '复盘概览',
    defaultSectionTitle: '复盘',
    reviewSummary: '复盘摘要',
    noReviewSummary: '暂无摘要',
    noSentimentScore: '暂无评分',
    rotationAndFunds: '轮动与资金',
    noRotationView: '暂无轮动观点',
    riskAndWatch: '风险与观察',
    noRiskWatch: '暂无观察重点',
    structuredMarketData: '结构化大盘数据',
    noBreadthData: '暂无数据',
    advancers: '上涨家数',
    decliners: '下跌家数',
    limitUpDown: '涨停/跌停',
    turnover: '成交额',
    index: '指数',
    last: '最新',
    change: '涨跌幅',
    highLow: '高/低',
    industryBoards: '行业板块',
    conceptBoards: '概念板块',
    leading: '领涨',
    lagging: '领跌',
  },
  en: {
    eyebrow: 'MARKET REVIEW',
    defaultTitle: 'Market Review',
    fullReview: 'Full Review',
    overview: 'Review Overview',
    defaultSectionTitle: 'Review',
    reviewSummary: 'Review Summary',
    noReviewSummary: 'No review summary yet',
    noSentimentScore: 'No score yet',
    rotationAndFunds: 'Rotation & Funds',
    noRotationView: 'No rotation view yet',
    riskAndWatch: 'Risks & Watchlist',
    noRiskWatch: 'No key observations yet',
    structuredMarketData: 'Structured Market Data',
    noBreadthData: 'No data',
    advancers: 'Advancers',
    decliners: 'Decliners',
    limitUpDown: 'Limit Up/Down',
    turnover: 'Turnover',
    index: 'Index',
    last: 'Last',
    change: 'Change',
    highLow: 'High/Low',
    industryBoards: 'Industry Sectors',
    conceptBoards: 'Concept Themes',
    leading: 'Leading',
    lagging: 'Lagging',
  },
  ko: {
    eyebrow: '시장 리뷰',
    defaultTitle: '시장 리뷰',
    fullReview: '전체 리뷰',
    overview: '리뷰 개요',
    defaultSectionTitle: '리뷰',
    reviewSummary: '리뷰 요약',
    noReviewSummary: '요약 없음',
    noSentimentScore: '점수 없음',
    rotationAndFunds: '순환과 자금',
    noRotationView: '순환 관점 없음',
    riskAndWatch: '리스크와 관찰',
    noRiskWatch: '관찰 포인트 없음',
    structuredMarketData: '구조화 시장 데이터',
    noBreadthData: '데이터 없음',
    advancers: '상승 종목 수',
    decliners: '하락 종목 수',
    limitUpDown: '상한가/하한가',
    turnover: '거래대금',
    index: '지수',
    last: '현재',
    change: '등락률',
    highLow: '고가/저가',
    industryBoards: '업종 섹터',
    conceptBoards: '테마 섹터',
    leading: '강세',
    lagging: '약세',
  },
};

type MarketStructureContent = {
  eyebrow: string;
  title: string;
  marketLayer: string;
  stockLayer: string;
  activeThemes: string;
  leadingConcepts: string;
  leadingIndustries: string;
  primaryTheme: string;
  themePhase: string;
  stockRole: string;
  riskTags: string;
  dataQuality: string;
  missingFields: string;
  empty: string;
  status: Record<MarketStructureStatus, string>;
  phase: Record<MarketStructureThemePhase, string>;
  role: Record<MarketStructureStockRole, string>;
  riskTag: Record<string, string>;
};

export const MARKET_STRUCTURE_CONTENT_TEXT: Record<ReportLanguage, MarketStructureContent> = {
  zh: {
    eyebrow: '市场位置',
    title: '题材主线与个股位置',
    marketLayer: '大盘题材层',
    stockLayer: '个股位置层',
    activeThemes: '活跃题材',
    leadingConcepts: '领涨概念',
    leadingIndustries: '领涨行业',
    primaryTheme: '主关联题材',
    themePhase: '题材阶段',
    stockRole: '个股位置',
    riskTags: '风险标签',
    dataQuality: '数据质量',
    missingFields: '缺失证据',
    empty: '暂无',
    status: {
      ok: '可用',
      partial: '部分可用',
      unknown: '未知',
      not_supported: '不支持',
    },
    phase: {
      warming: '升温',
      accelerating: '加速',
      cooling: '降温',
      unknown: '未知',
    },
    role: {
      leader: '龙头',
      follower: '跟随',
      edge: '边缘关联',
      unknown: '未知',
    },
    riskTag: {
      theme_data_partial: '题材主线数据不完整',
      stock_theme_evidence_partial: '个股板块未匹配到市场题材榜单，个股位置按降级证据处理',
      board_membership_missing: '缺少个股所属板块证据，无法判断题材位置',
    },
  },
  en: {
    eyebrow: 'MARKET POSITION',
    title: 'Themes and Stock Position',
    marketLayer: 'Market Theme Layer',
    stockLayer: 'Stock Position Layer',
    activeThemes: 'Active Themes',
    leadingConcepts: 'Leading Concepts',
    leadingIndustries: 'Leading Industries',
    primaryTheme: 'Primary Theme',
    themePhase: 'Theme Phase',
    stockRole: 'Stock Role',
    riskTags: 'Risk Tags',
    dataQuality: 'Data Quality',
    missingFields: 'Missing Evidence',
    empty: 'None',
    status: {
      ok: 'Available',
      partial: 'Partial',
      unknown: 'Unknown',
      not_supported: 'Not supported',
    },
    phase: {
      warming: 'Warming',
      accelerating: 'Accelerating',
      cooling: 'Cooling',
      unknown: 'Unknown',
    },
    role: {
      leader: 'Leader',
      follower: 'Follower',
      edge: 'Edge',
      unknown: 'Unknown',
    },
    riskTag: {
      theme_data_partial: 'Market theme data is incomplete',
      stock_theme_evidence_partial: 'Stock board did not match theme rankings',
      board_membership_missing: 'Stock board membership evidence is missing',
    },
  },
  ko: {
    eyebrow: '시장 포지션',
    title: '테마 라인 및 종목 포지션',
    marketLayer: '시장 테마 레이어',
    stockLayer: '종목 포지션 레이어',
    activeThemes: '활성 테마',
    leadingConcepts: '선도 테마',
    leadingIndustries: '선도 산업',
    primaryTheme: '주요 관련 테마',
    themePhase: '테마 단계',
    stockRole: '종목 역할',
    riskTags: '리스크 태그',
    dataQuality: '데이터 품질',
    missingFields: '부족한 근거',
    empty: '없음',
    status: {
      ok: '사용 가능',
      partial: '일부 사용',
      unknown: '알 수 없음',
      not_supported: '미지원',
    },
    phase: {
      warming: '온도 상승',
      accelerating: '가속',
      cooling: '쿨다운',
      unknown: '알 수 없음',
    },
    role: {
      leader: '리더',
      follower: '추종',
      edge: '엣지',
      unknown: '알 수 없음',
    },
    riskTag: {
      theme_data_partial: '테마 데이터가 불완전합니다',
      stock_theme_evidence_partial: '종목 보드가 테마 랭킹과 일치하지 않았습니다',
      board_membership_missing: '종목 보드 근거가 없어 테마 위치를 판단할 수 없습니다',
    },
  },
};

type ReportNewsContent = {
  sourceLabel: string;
  sourceHint: string;
};

export const REPORT_NEWS_CONTENT_TEXT: Record<ReportLanguage, ReportNewsContent> = {
  zh: {
    sourceLabel: '相关资讯/后续检索',
    sourceHint: '来源：报告页补充资讯；是否用于分析以输入数据块为准。',
  },
  en: {
    sourceLabel: 'Related news / follow-up retrieval',
    sourceHint: 'Source: supplemental report-page news; analysis input is shown in Input Blocks.',
  },
  ko: {
    sourceLabel: '관련 뉴스 / 후속 검색',
    sourceHint: '출처: 리포트 페이지 보충 뉴스이며, 분석 사용 여부는 입력 데이터 블록 기준입니다.',
  },
};
