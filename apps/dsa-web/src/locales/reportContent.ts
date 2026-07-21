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
  sourceUnavailable: string;
  warnings: string;
  details: string;
  diagnosticCode: string;
  diagnosticCodeUnavailable: string;
  unknownReasonDetails: string;
  inputScope: string;
  evidenceScope: string;
  qualityScore: string;
  limitations: string;
  newsResultCount: string;
  triggerSource: string;
  qualityLevel: Record<QualityLevel, string>;
  status: Record<AnalysisContextPackBlockStatus, string>;
  statusGuidance: Partial<Record<AnalysisContextPackBlockStatus, string>>;
  blockLabels: Record<string, string>;
  missingReasonLabels: Record<string, string>;
};

export const ANALYSIS_CONTEXT_CONTENT_TEXT: Record<ReportLanguage, AnalysisContextContent> = {
  zh: {
    eyebrow: '数据上下文',
    title: '输入数据块',
    counts: '状态计数',
    source: '来源',
    sourceUnavailable: '未记录输入来源',
    warnings: '告警',
    details: '说明',
    diagnosticCode: '诊断码',
    diagnosticCodeUnavailable: '不可用',
    unknownReasonDetails: '未记录明确原因；请结合状态、来源和告警排查',
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
    statusGuidance: {
      missing: '数据未进入本次分析，相关结论可能不完整；请检查数据源、配置或网络后重新分析',
      fetch_failed: '数据抓取失败，本次分析未使用该数据；请检查数据源、网络或限流后重新分析',
      not_supported: '当前市场或标的不支持该数据，本次分析未使用该数据；请结合其他指标判断',
      fallback: '本次分析使用了备用数据路径；请结合来源和告警复核结果',
      stale: '本次分析使用的不是最新数据；请检查更新时间并按需重新分析',
      estimated: '本次分析使用了估算数据；请结合原始数据复核结果',
      partial: '仅部分数据进入本次分析，相关结论可能不完整；请检查告警和数据源后重新分析',
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
      daily_bars_missing: '日线数据未进入本次分析，技术指标可能不完整；请检查日线数据源、网络或限流后重新分析',
      news_context_missing: '新闻未进入本次 LLM 分析，结论未使用新闻上下文；报告页相关资讯由独立接口补充，显示与否不代表已进入本次分析。请检查搜索配置、网络或限流后重新分析',
      realtime_quote_missing: '实时行情未进入本次分析，当前价格相关结论可能受限；请检查行情数据源、网络或限流后重新分析',
      trend_result_missing: '技术分析结果未进入本次分析，技术面判断可能不完整；请检查日线完整性后重新分析',
      fundamental_context_missing: '基本面未进入本次分析，结论未使用基本面数据；请检查基本面数据源、网络或限流后重新分析',
      fundamental_pipeline_failed: '基本面抓取失败，本次分析未使用基本面数据；请检查数据源配置、网络或限流后重新分析',
      fundamentals_not_supported: '当前市场或标的不支持基本面数据，本次分析未使用该数据；请结合其他指标判断',
      fundamental_coverage_missing: '基本面覆盖数据未进入本次分析，结论可能缺少部分财务信息；请检查数据源覆盖范围后重新分析',
      fundamental_source_chain_missing: '未记录基本面来源链元数据；基本面是否进入本次分析以当前状态为准，请结合来源和告警复核数据出处',
      chip_distribution_missing: '筹码数据未进入本次分析，结论未使用筹码分布；请确认当前市场或标的数据支持情况',
      chip_not_supported: '当前市场或标的不支持筹码数据，本次分析未使用该指标；请结合其他指标判断',
      today_missing: '今日数据未进入本次分析，盘中判断可能受限；请结合实时行情复核后重新分析',
      yesterday_missing: '昨日数据未进入本次分析，日线对比可能不完整；请等待数据源更新后重新分析',
    },
  },
  en: {
    eyebrow: 'DATA CONTEXT',
    title: 'Input Blocks',
    counts: 'Status Counts',
    source: 'Source',
    sourceUnavailable: 'Input source not recorded',
    warnings: 'Warnings',
    details: 'Details',
    diagnosticCode: 'Diagnostic code',
    diagnosticCodeUnavailable: 'unavailable',
    unknownReasonDetails: 'No specific reason was recorded; review the status, source, and warnings',
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
    statusGuidance: {
      missing: 'Data was not included, so related conclusions may be incomplete; check the data source, configuration, or network and rerun',
      fetch_failed: 'Data retrieval failed and this analysis did not use the data; check the source, network, or rate limits and rerun',
      not_supported: 'This data is not supported for the current market or symbol and was not used; cross-check other indicators',
      fallback: 'This analysis used a fallback data path; review the result against its source and warnings',
      stale: 'This analysis used data that may not be current; check the timestamp and rerun if needed',
      estimated: 'This analysis used estimated data; cross-check the result against source data',
      partial: 'Only part of the data was included, so related conclusions may be incomplete; check warnings and the data source and rerun',
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
      daily_bars_missing: 'Daily bars were not included, so technical indicators may be incomplete; check the daily data source, network, or rate limits and rerun',
      news_context_missing: 'News was not included in this LLM run, so the conclusion did not use news context; related news on the report page is loaded separately and does not indicate that it was used in this analysis. Check search configuration, network, or rate limits and rerun',
      realtime_quote_missing: 'Real-time quotes were not included, so price-related conclusions may be limited; check the quote source, network, or rate limits and rerun',
      trend_result_missing: 'Technical analysis was not included, so the technical view may be incomplete; check daily-bar completeness and rerun',
      fundamental_context_missing: 'Fundamentals were not included, so the conclusion did not use fundamental data; check the data source, network, or rate limits and rerun',
      fundamental_pipeline_failed: 'Fundamental retrieval failed and this analysis did not use fundamental data; check the data-source configuration, network, or rate limits and rerun',
      fundamentals_not_supported: 'Fundamental data is not supported for this market or symbol and was not used; cross-check other indicators',
      fundamental_coverage_missing: 'Fundamental coverage was not included, so some financial context may be missing; check source coverage and rerun',
      fundamental_source_chain_missing: 'Fundamental source-chain metadata was not recorded; use the current status to determine whether fundamentals were included, and review the source and warnings for provenance',
      chip_distribution_missing: 'Chip distribution was not included and was not used in the conclusion; confirm support for this market or symbol',
      chip_not_supported: 'Chip data is not supported for this market or symbol and was not used; cross-check other indicators',
      today_missing: "Today's data was not included, so intraday conclusions may be limited; cross-check real-time quotes and rerun",
      yesterday_missing: "Yesterday's data was not included, so daily comparisons may be incomplete; wait for the source to update and rerun",
    },
  },
  ko: {
    eyebrow: '정보 컨텍스트',
    title: '입력 데이터 블록',
    counts: '상태 카운트',
    source: '출처',
    sourceUnavailable: '입력 출처 기록 없음',
    warnings: '경고',
    details: '설명',
    diagnosticCode: '진단 코드',
    diagnosticCodeUnavailable: '사용 불가',
    unknownReasonDetails: '명확한 원인이 기록되지 않았습니다. 상태, 출처 및 경고를 함께 확인하세요',
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
    statusGuidance: {
      missing: '데이터가 포함되지 않아 관련 결론이 불완전할 수 있습니다. 데이터 소스, 설정 또는 네트워크를 확인한 후 다시 분석하세요',
      fetch_failed: '데이터 수집에 실패해 이번 분석에서 사용되지 않았습니다. 데이터 소스, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      not_supported: '현재 시장 또는 종목은 이 데이터를 지원하지 않아 분석에 사용되지 않았습니다. 다른 지표와 함께 판단하세요',
      fallback: '이번 분석은 대체 데이터 경로를 사용했습니다. 출처와 경고를 기준으로 결과를 검토하세요',
      stale: '이번 분석은 최신이 아닐 수 있는 데이터를 사용했습니다. 갱신 시각을 확인하고 필요하면 다시 분석하세요',
      estimated: '이번 분석은 추정 데이터를 사용했습니다. 원본 데이터와 결과를 교차 확인하세요',
      partial: '데이터의 일부만 포함되어 관련 결론이 불완전할 수 있습니다. 경고와 데이터 소스를 확인한 후 다시 분석하세요',
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
      daily_bars_missing: '일봉이 포함되지 않아 기술 지표가 불완전할 수 있습니다. 일봉 소스, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      news_context_missing: '뉴스가 이번 LLM 분석에 포함되지 않아 결론에 뉴스 맥락이 반영되지 않았습니다. 보고서 페이지의 관련 뉴스는 별도 API에서 불러오며, 표시 여부가 이번 분석에 사용되었음을 의미하지는 않습니다. 검색 설정, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      realtime_quote_missing: '실시간 시세가 포함되지 않아 가격 관련 결론이 제한될 수 있습니다. 시세 소스, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      trend_result_missing: '기술 분석 결과가 포함되지 않아 기술적 판단이 불완전할 수 있습니다. 일봉 완전성을 확인한 후 다시 분석하세요',
      fundamental_context_missing: '펀더멘털이 포함되지 않아 결론에 펀더멘털 데이터가 반영되지 않았습니다. 데이터 소스, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      fundamental_pipeline_failed: '펀더멘털 수집에 실패해 이번 분석에서 사용되지 않았습니다. 데이터 소스 설정, 네트워크 또는 제한을 확인한 후 다시 분석하세요',
      fundamentals_not_supported: '현재 시장 또는 종목은 펀더멘털 데이터를 지원하지 않아 분석에 사용되지 않았습니다. 다른 지표와 함께 판단하세요',
      fundamental_coverage_missing: '펀더멘털 커버리지가 포함되지 않아 일부 재무 맥락이 빠질 수 있습니다. 소스 범위를 확인한 후 다시 분석하세요',
      fundamental_source_chain_missing: '펀더멘털 소스 체인 메타데이터가 기록되지 않았습니다. 펀더멘털 포함 여부는 현재 상태를 기준으로 판단하고 출처와 경고를 함께 확인하세요',
      chip_distribution_missing: '매물대 데이터가 포함되지 않아 결론에 반영되지 않았습니다. 현재 시장 또는 종목의 지원 여부를 확인하세요',
      chip_not_supported: '현재 시장 또는 종목은 매물대 데이터를 지원하지 않아 분석에 사용되지 않았습니다. 다른 지표와 함께 판단하세요',
      today_missing: '당일 데이터가 포함되지 않아 장중 판단이 제한될 수 있습니다. 실시간 시세와 대조한 후 다시 분석하세요',
      yesterday_missing: '전일 데이터가 포함되지 않아 일봉 비교가 불완전할 수 있습니다. 소스 갱신 후 다시 분석하세요',
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
