// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReportLanguage } from '../types/analysis';

type StructuredInsightContent = {
  phaseEyebrow: string;
  phaseTitle: string;
  marketPhase: string;
  immediateAction: string;
  actionWindow: string;
  nextCheckTime: string;
  confidenceReason: string;
  watchConditions: string;
  dataLimitations: string;
  contextWarnings: string;
  triggerSource: string;
  analysisIntent: string;
  attributionEyebrow: string;
  attributionTitle: string;
  strongestBullish: string;
  strongestBearish: string;
  synthesisEyebrow: string;
  synthesisTitle: string;
  finalSignal: string;
  weightedScore: string;
  confidence: string;
  consensus: string;
  conflictSeverity: string;
  conflicts: string;
  supportingSkills: string;
  opposingSkills: string;
  invalidOpinions: string;
  participants: string;
  noParticipants: string;
  attributionLabels: Record<string, string>;
  phaseLabels: Record<string, string>;
  signalLabels: Record<string, string>;
  consensusLabels: Record<string, string>;
  severityLabels: Record<string, string>;
  conflictLabels: Record<string, string>;
};

export const REPORT_STRUCTURED_INSIGHTS_TEXT: Record<
  ReportLanguage,
  StructuredInsightContent
> = {
  zh: {
    phaseEyebrow: '决策时点',
    phaseTitle: '阶段决策',
    marketPhase: '市场阶段',
    immediateAction: '当前动作',
    actionWindow: '行动窗口',
    nextCheckTime: '下次检查',
    confidenceReason: '判断依据',
    watchConditions: '观察条件',
    dataLimitations: '数据限制',
    contextWarnings: '阶段提醒',
    triggerSource: '触发来源',
    analysisIntent: '分析意图',
    attributionEyebrow: '结论来源',
    attributionTitle: '信号归因',
    strongestBullish: '最强看多证据',
    strongestBearish: '最强看空证据',
    synthesisEyebrow: '多策略汇总',
    synthesisTitle: '策略综合',
    finalSignal: '综合信号',
    weightedScore: '加权分',
    confidence: '置信度',
    consensus: '共识',
    conflictSeverity: '冲突等级',
    conflicts: '策略冲突',
    supportingSkills: '支持策略',
    opposingSkills: '反方策略',
    invalidOpinions: '未采纳意见',
    participants: '涉及策略',
    noParticipants: '未记录',
    attributionLabels: {
      technicalIndicators: '技术指标',
      newsSentiment: '新闻情绪',
      fundamentals: '基本面',
      marketConditions: '市场环境',
    },
    phaseLabels: {
      premarket: '盘前',
      intraday: '盘中',
      lunch_break: '午间休市',
      closing_auction: '收盘集合竞价',
      postmarket: '盘后',
      non_trading: '非交易时段',
      unknown: '未知',
    },
    signalLabels: {
      strong_buy: '强力买入',
      buy: '买入',
      add: '加仓',
      hold: '持有',
      reduce: '减仓',
      sell: '卖出',
      watch: '观望',
      avoid: '回避',
    },
    consensusLabels: {
      high: '高',
      medium: '中',
      low: '低',
      insufficient: '证据不足',
    },
    severityLabels: {
      none: '无',
      low: '低',
      medium: '中',
      high: '高',
    },
    conflictLabels: {
      directional_opposition: '策略方向相反',
      wide_score_dispersion: '策略评分分散',
      high_confidence_dissent: '高置信反方意见',
      adjustment_contradiction: '评分调整相互矛盾',
    },
  },
  en: {
    phaseEyebrow: 'DECISION TIMING',
    phaseTitle: 'Phase Decision',
    marketPhase: 'Market Phase',
    immediateAction: 'Immediate Action',
    actionWindow: 'Action Window',
    nextCheckTime: 'Next Check',
    confidenceReason: 'Rationale',
    watchConditions: 'Watch Conditions',
    dataLimitations: 'Data Limitations',
    contextWarnings: 'Phase Warnings',
    triggerSource: 'Trigger',
    analysisIntent: 'Analysis Intent',
    attributionEyebrow: 'CONCLUSION INPUTS',
    attributionTitle: 'Signal Attribution',
    strongestBullish: 'Strongest Bullish Evidence',
    strongestBearish: 'Strongest Bearish Evidence',
    synthesisEyebrow: 'MULTI-STRATEGY',
    synthesisTitle: 'Strategy Synthesis',
    finalSignal: 'Final Signal',
    weightedScore: 'Weighted Score',
    confidence: 'Confidence',
    consensus: 'Consensus',
    conflictSeverity: 'Conflict Severity',
    conflicts: 'Strategy Conflicts',
    supportingSkills: 'Supporting Strategies',
    opposingSkills: 'Opposing Strategies',
    invalidOpinions: 'Excluded Opinions',
    participants: 'Strategies',
    noParticipants: 'Not recorded',
    attributionLabels: {
      technicalIndicators: 'Technical Indicators',
      newsSentiment: 'News Sentiment',
      fundamentals: 'Fundamentals',
      marketConditions: 'Market Conditions',
    },
    phaseLabels: {
      premarket: 'Premarket',
      intraday: 'Intraday',
      lunch_break: 'Lunch Break',
      closing_auction: 'Closing Auction',
      postmarket: 'Postmarket',
      non_trading: 'Non-trading',
      unknown: 'Unknown',
    },
    signalLabels: {
      strong_buy: 'Strong Buy',
      buy: 'Buy',
      add: 'Add',
      hold: 'Hold',
      reduce: 'Reduce',
      sell: 'Sell',
      watch: 'Watch',
      avoid: 'Avoid',
    },
    consensusLabels: {
      high: 'High',
      medium: 'Medium',
      low: 'Low',
      insufficient: 'Insufficient',
    },
    severityLabels: {
      none: 'None',
      low: 'Low',
      medium: 'Medium',
      high: 'High',
    },
    conflictLabels: {
      directional_opposition: 'Opposing strategy directions',
      wide_score_dispersion: 'Wide score dispersion',
      high_confidence_dissent: 'High-confidence dissent',
      adjustment_contradiction: 'Contradictory score adjustments',
    },
  },
  ko: {
    phaseEyebrow: '판단 시점',
    phaseTitle: '단계별 판단',
    marketPhase: '시장 단계',
    immediateAction: '현재 행동',
    actionWindow: '행동 구간',
    nextCheckTime: '다음 확인',
    confidenceReason: '판단 근거',
    watchConditions: '관찰 조건',
    dataLimitations: '데이터 한계',
    contextWarnings: '단계 경고',
    triggerSource: '트리거',
    analysisIntent: '분석 의도',
    attributionEyebrow: '결론 입력',
    attributionTitle: '신호 기여도',
    strongestBullish: '가장 강한 상승 근거',
    strongestBearish: '가장 강한 하락 근거',
    synthesisEyebrow: '다중 전략 요약',
    synthesisTitle: '전략 종합',
    finalSignal: '종합 신호',
    weightedScore: '가중 점수',
    confidence: '확신도',
    consensus: '합의 수준',
    conflictSeverity: '충돌 수준',
    conflicts: '전략 충돌',
    supportingSkills: '지지 전략',
    opposingSkills: '반대 전략',
    invalidOpinions: '제외된 의견',
    participants: '관련 전략',
    noParticipants: '기록 없음',
    attributionLabels: {
      technicalIndicators: '기술 지표',
      newsSentiment: '뉴스 심리',
      fundamentals: '펀더멘털',
      marketConditions: '시장 환경',
    },
    phaseLabels: {
      premarket: '장전',
      intraday: '장중',
      lunch_break: '점심 휴장',
      closing_auction: '마감 동시호가',
      postmarket: '장후',
      non_trading: '비거래 시간',
      unknown: '알 수 없음',
    },
    signalLabels: {
      strong_buy: '강력 매수',
      buy: '매수',
      add: '추가 매수',
      hold: '보유',
      reduce: '비중 축소',
      sell: '매도',
      watch: '관망',
      avoid: '회피',
    },
    consensusLabels: {
      high: '높음',
      medium: '보통',
      low: '낮음',
      insufficient: '근거 부족',
    },
    severityLabels: {
      none: '없음',
      low: '낮음',
      medium: '보통',
      high: '높음',
    },
    conflictLabels: {
      directional_opposition: '전략 방향 대립',
      wide_score_dispersion: '전략 점수 분산',
      high_confidence_dissent: '높은 확신도의 반대 의견',
      adjustment_contradiction: '점수 조정 방향 충돌',
    },
  },
};
