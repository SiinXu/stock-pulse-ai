import type { UiLanguage } from '../i18n/uiText';

type StrategyText = {
  name: string;
  description: string;
  category: string;
};

type StrategyTextRegistry = Record<string, StrategyText>;

const zh: StrategyTextRegistry = {
  balanced_alpha: { name: '均衡多因子', description: '综合估值、资金、动量与稳定性的通用候选发现策略。', category: '分析框架' },
  blue_chip_income: { name: '蓝筹收益质量', description: '筛选估值合理、成交稳定且偏防守的大盘蓝筹候选。', category: '收益质量' },
  bottom_volume: { name: '底部放量', description: '检测长期下跌后的底部放量信号，识别潜在趋势反转。', category: '反转' },
  box_oscillation: { name: '箱体震荡', description: '识别价格箱体，在支撑与阻力之间寻找区间机会。', category: '分析框架' },
  bull_trend: { name: '默认多头趋势', description: '识别多头排列、趋势延续与回踩低吸机会。', category: '趋势' },
  capital_heat: { name: '资金热度', description: '筛选资金活跃、量价同步且未极端过热的短线候选。', category: '动量' },
  chan_theory: { name: '缠论', description: '基于笔、线段与中枢结构判断趋势级别和买卖点。', category: '分析框架' },
  dragon_head: { name: '龙头策略', description: '在板块轮动中识别率先启动并具备持续性的龙头股。', category: '趋势' },
  dual_low: { name: '双低选股', description: '结合低估值、活跃度与形态确认筛选偏稳健候选。', category: '价值' },
  emotion_cycle: { name: '情绪周期', description: '结合市场情绪、换手率与量价结构识别周期位置。', category: '分析框架' },
  event_driven: { name: '事件驱动', description: '围绕业绩、政策、并购和订单等事件评估催化与风险。', category: '分析框架' },
  expectation_repricing: { name: '预期重估', description: '分析业绩、政策与估值预期变化，识别预期差和过热风险。', category: '分析框架' },
  growth_quality: { name: '成长质量', description: '结合增长、ROE、现金流与行业空间识别高质量成长。', category: '分析框架' },
  hot_theme: { name: '热点题材', description: '跟踪政策、产业和市场热点，判断题材强度与相对位置。', category: '分析框架' },
  low_volatility_quality: { name: '低波质量', description: '优先选择波动较低、回撤较浅且数据质量可靠的候选。', category: '质量' },
  ma_golden_cross: { name: '均线金叉', description: '检测均线金叉与量能确认形成的趋势反转或延续信号。', category: '趋势' },
  momentum_quality: { name: '趋势质量', description: '兼顾趋势确认与基本面质量的中线候选发现策略。', category: '分析框架' },
  one_yang_three_yin: { name: '一阳夹三阴', description: '检测一阳夹三阴的 K 线整理形态与趋势延续信号。', category: '形态' },
  oversold_reversal: { name: '超跌反转', description: '筛选跌幅可控、流动性仍在且具备修复价值的候选。', category: '反转' },
  quality_value: { name: '稳健价值', description: '筛选估值合理、流动性充足且不过热的稳健候选。', category: '价值' },
  shrink_pullback: { name: '缩量回踩', description: '识别上升趋势中缩量回踩均线支撑的延续机会。', category: '趋势' },
  volume_breakout: { name: '放量突破', description: '检测成交量放大并突破关键阻力位的趋势启动信号。', category: '趋势' },
  wave_theory: { name: '波浪理论', description: '基于推动浪与调整浪结构判断趋势位置和潜在目标。', category: '分析框架' },
};

const en: StrategyTextRegistry = {
  balanced_alpha: { name: 'Balanced Multi-Factor', description: 'Combines valuation, capital flow, momentum, and stability to find balanced candidates.', category: 'Framework' },
  blue_chip_income: { name: 'Blue-Chip Income Quality', description: 'Finds liquid, reasonably valued large caps suited to defensive holding.', category: 'Income quality' },
  bottom_volume: { name: 'Bottom Volume Surge', description: 'Detects a volume surge after a prolonged decline as a potential reversal signal.', category: 'Reversal' },
  box_oscillation: { name: 'Box Range Trading', description: 'Identifies price ranges and opportunities between support and resistance.', category: 'Framework' },
  bull_trend: { name: 'Bull Trend', description: 'Identifies bullish alignment, trend continuation, and pullback entries.', category: 'Trend' },
  capital_heat: { name: 'Capital Heat', description: 'Finds active short-term candidates with aligned price and volume before overheating.', category: 'Momentum' },
  chan_theory: { name: 'Chan Theory', description: 'Uses strokes, segments, and central zones to identify trend levels and trade points.', category: 'Framework' },
  dragon_head: { name: 'Sector Leader', description: 'Identifies early, durable leaders during sector rotation.', category: 'Trend' },
  dual_low: { name: 'Dual-Low Selection', description: 'Combines low valuation, activity, and pattern confirmation for defensive candidates.', category: 'Value' },
  emotion_cycle: { name: 'Sentiment Cycle', description: 'Uses sentiment, turnover, price, and volume to identify the market cycle stage.', category: 'Framework' },
  event_driven: { name: 'Event Driven', description: 'Evaluates catalysts and risks around earnings, policy, M&A, and major orders.', category: 'Framework' },
  expectation_repricing: { name: 'Expectation Repricing', description: 'Tracks changes in earnings, policy, and valuation expectations.', category: 'Framework' },
  growth_quality: { name: 'Growth Quality', description: 'Combines growth, ROE, cash flow, and industry runway to assess quality.', category: 'Framework' },
  hot_theme: { name: 'Hot Theme', description: 'Tracks policy, industry, and market themes to assess strength and relative position.', category: 'Framework' },
  low_volatility_quality: { name: 'Low-Volatility Quality', description: 'Prioritizes reliable candidates with lower volatility and shallower drawdowns.', category: 'Quality' },
  ma_golden_cross: { name: 'MA Golden Cross', description: 'Detects moving-average crosses confirmed by volume for reversal or continuation.', category: 'Trend' },
  momentum_quality: { name: 'Momentum Quality', description: 'Combines trend confirmation and fundamental quality for swing candidates.', category: 'Framework' },
  one_yang_three_yin: { name: 'One Yang, Three Yin', description: 'Detects a consolidation candlestick pattern that may precede trend continuation.', category: 'Pattern' },
  oversold_reversal: { name: 'Oversold Reversal', description: 'Finds controlled declines with sufficient liquidity and recovery potential.', category: 'Reversal' },
  quality_value: { name: 'Quality Value', description: 'Finds reasonably valued, liquid, and stable candidates that are not overheated.', category: 'Value' },
  shrink_pullback: { name: 'Volume-Contraction Pullback', description: 'Finds low-volume pullbacks to moving-average support within an uptrend.', category: 'Trend' },
  volume_breakout: { name: 'Volume Breakout', description: 'Detects high-volume breaks above key resistance as a trend-start signal.', category: 'Trend' },
  wave_theory: { name: 'Elliott Wave', description: 'Uses impulse and corrective wave structures to assess trend position and targets.', category: 'Framework' },
};

export const BUILTIN_STRATEGY_TEXT: Record<UiLanguage, StrategyTextRegistry> = { zh, en };
