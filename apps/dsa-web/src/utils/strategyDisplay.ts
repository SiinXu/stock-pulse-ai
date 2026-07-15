import type { UiLanguage } from '../i18n/uiText';

export type StrategyDisplaySource = {
  id: string;
  name?: string | null;
  nameZh?: string | null;
  nameEn?: string | null;
  title?: string | null;
  titleZh?: string | null;
  titleEn?: string | null;
  description?: string | null;
  descriptionZh?: string | null;
  descriptionEn?: string | null;
  category?: string | null;
  categoryZh?: string | null;
  categoryEn?: string | null;
  tag?: string | null;
  tags?: string[] | null;
};

export type StrategyDisplay = {
  name: string;
  description: string;
  category: string;
};

type LocalizedStrategyCopy = Record<UiLanguage, StrategyDisplay>;

const copy = (
  zhName: string,
  enName: string,
  zhDescription: string,
  enDescription: string,
  zhCategory: string,
  enCategory: string,
): LocalizedStrategyCopy => ({
  zh: { name: zhName, description: zhDescription, category: zhCategory },
  en: { name: enName, description: enDescription, category: enCategory },
});

// IDs are the contract. Server-provided display strings are never used to
// decide whether a strategy is built in.
const BUILTIN_STRATEGY_COPY: Record<string, LocalizedStrategyCopy> = {
  balanced_alpha: copy('平衡选股', 'Balanced selection', '平衡估值、质量和动量因子。', 'Balances valuation, quality, and momentum factors.', '综合', 'Balanced'),
  capital_heat: copy('资金热度', 'Capital heat', '跟踪资金活跃度和市场热度。', 'Tracks capital activity and market heat.', '动量', 'Momentum'),
  dual_low: copy('双低选股', 'Dual-low selection', '筛选价格与估值相对较低的候选。', 'Screens for candidates with relatively low price and valuation.', '价值', 'Value'),
  oversold_reversal: copy('超跌反转', 'Oversold reversal', '寻找超跌后的修复与反转机会。', 'Looks for recovery and reversal after an oversold move.', '反转', 'Reversal'),
  bull_trend: copy('默认多头趋势', 'Default bull trend', '识别多头排列、趋势延续与回踩机会。', 'Identifies bullish alignment, trend continuation, and pullback opportunities.', '趋势', 'Trend'),
  shrink_pullback: copy('缩量回踩', 'Low-volume pullback', '检测缩量回踩均线支撑信号。', 'Detects low-volume pullbacks into moving-average support.', '趋势', 'Trend'),
  dragon_head: copy('龙头策略', 'Sector leader', '在板块轮动中识别龙头股。', 'Identifies leading stocks during sector rotation.', '趋势', 'Trend'),
  growth_quality: copy('成长质量', 'Growth quality', '结合增长、ROE、现金流和行业空间评估成长质量。', 'Evaluates growth quality using growth, ROE, cash flow, and industry runway.', '基本面', 'Fundamental'),
  hot_theme: copy('热点题材', 'Hot themes', '跟踪政策、产业和市场热点。', 'Tracks policy, industry, and market themes.', '综合', 'Framework'),
  event_driven: copy('事件驱动', 'Event driven', '评估事件催化、兑现概率和风险边界。', 'Evaluates event catalysts, realization probability, and risk boundaries.', '综合', 'Framework'),
  expectation_repricing: copy('预期重估', 'Expectation repricing', '分析业绩、政策和估值预期变化。', 'Analyzes changes in earnings, policy, and valuation expectations.', '综合', 'Framework'),
  ma_golden_cross: copy('均线金叉', 'MA golden cross', '检测均线金叉和量能确认信号。', 'Detects moving-average crosses with volume confirmation.', '趋势', 'Trend'),
  volume_breakout: copy('放量突破', 'Volume breakout', '检测放量突破阻力位信号。', 'Detects resistance breakouts confirmed by volume.', '趋势', 'Trend'),
  bottom_volume: copy('底部放量', 'Bottom volume surge', '检测长期下跌后的底部放量信号。', 'Detects volume expansion near a potential bottom after a prolonged decline.', '反转', 'Reversal'),
  box_oscillation: copy('箱体震荡', 'Box range trading', '识别箱体支撑与阻力区间。', 'Identifies support and resistance within a trading range.', '综合', 'Framework'),
  chan_theory: copy('缠论', 'Chan theory', '基于笔、线段和中枢结构分析趋势。', 'Analyzes trends using strokes, segments, and central structures.', '综合', 'Framework'),
  wave_theory: copy('波浪理论', 'Elliott wave', '分析推动浪与调整浪结构。', 'Analyzes impulse and corrective wave structures.', '综合', 'Framework'),
  emotion_cycle: copy('情绪周期', 'Sentiment cycle', '基于市场情绪与量价结构识别周期位置。', 'Uses market sentiment and price-volume structure to locate the cycle stage.', '综合', 'Framework'),
  one_yang_three_yin: copy('一阳夹三阴', 'One bullish, three bearish', '检测一阳夹三阴整理形态。', 'Detects the one-bullish, three-bearish consolidation pattern.', '形态', 'Pattern'),
};

function firstText(...values: Array<string | null | undefined>): string {
  return values.find((value) => typeof value === 'string' && value.trim())?.trim() ?? '';
}

export function getStrategyDisplay(source: StrategyDisplaySource, language: UiLanguage): StrategyDisplay {
  const builtin = BUILTIN_STRATEGY_COPY[source.id]?.[language];
  const localizedName = language === 'en'
    ? firstText(source.nameEn, source.titleEn)
    : firstText(source.nameZh, source.titleZh);
  const localizedDescription = language === 'en' ? source.descriptionEn : source.descriptionZh;
  const localizedCategory = language === 'en' ? source.categoryEn : source.categoryZh;
  const rawName = firstText(source.name, source.title);
  const rawCategory = firstText(source.category, source.tag, source.tags?.[0]);
  return {
    name: language === 'en'
      ? firstText(localizedName, builtin?.name, rawName, source.id)
      : firstText(localizedName, rawName, builtin?.name, source.id),
    description: language === 'en'
      ? firstText(localizedDescription, builtin?.description, source.description, source.id)
      : firstText(localizedDescription, source.description, builtin?.description, source.id),
    category: language === 'en'
      ? firstText(localizedCategory, builtin?.category, rawCategory, source.id)
      : firstText(localizedCategory, rawCategory, builtin?.category, source.id),
  };
}
