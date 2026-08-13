// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SettingsHelpMap } from './settingsHelpTypes';

const educationHelpEnUS: SettingsHelpMap = {
  'education.risk.level.low': {
    title: 'Low risk level',
    summary: 'A relative score band under 25 on a 0–100 scale used in portfolio risk heatmaps.',
    usage: 'Shown when weight, stop-loss proximity, or from-peak loss pressure is still mild versus other holdings.',
    impact: [
      'Treat this as a quieter structural reading, not a guarantee of safety or a buy signal.',
    ],
    notes: [
      'Low does not mean zero risk; a single market event can move any name higher.',
    ],
  },
  'education.risk.level.medium': {
    title: 'Medium risk level',
    summary: 'A mid band (about 25–49) on the 0–100 portfolio risk score scale.',
    usage: 'Appears when concentration, stop-loss distance, or from-peak loss is elevated but not extreme.',
    impact: [
      'Worth a second look: size, stop levels, and diversification may need attention before adding risk.',
    ],
  },
  'education.risk.level.high': {
    title: 'Elevated risk level',
    summary: 'A higher band (about 50–74) on the 0–100 portfolio risk score scale.',
    usage: 'Triggered when structural pressure is clearly stronger than the quieter holdings in the same view.',
    impact: [
      'Prefer reviewing position size and exit plan before treating the idea as routine.',
    ],
  },
  'education.risk.level.critical': {
    title: 'High risk level',
    summary: 'The top band (about 75–100) on the 0–100 portfolio risk score scale.',
    usage: 'Reserved for the strongest structural pressure in the heatmap (weight, stop-loss, or from-peak loss).',
    impact: [
      'Treat as a priority review: do not ignore size, stops, or correlation with the rest of the book.',
    ],
    notes: [
      'Color alone is not enough—read the score, label, and underlying metric together.',
    ],
  },
  'education.risk.beginner.elevated': {
    title: 'Elevated beginner risk',
    summary: 'A simplified label when the published action leans defensive (reduce, sell, avoid, or alert).',
    usage: 'Beginner mode maps action families to a short risk tag so you can scan without reading every metric.',
    impact: [
      'Slow down: prefer smaller size, clearer stops, or wait for a calmer setup before acting.',
    ],
    notes: [
      'This is research framing, not a personal suitability assessment or investment advice.',
    ],
  },
  'education.risk.beginner.moderate': {
    title: 'Moderate beginner risk',
    summary: 'A simplified label when the published action is constructive or neutral (buy, add, hold, watch).',
    usage: 'Used in beginner summaries so risk stays visible even when the action is not defensive.',
    impact: [
      'Still require a plan: size, invalidation, and data limits matter even on moderate tags.',
    ],
  },
  'education.risk.beginner.unrated': {
    title: 'Risk not assessed',
    summary: 'No simplified risk band could be derived from the current action field.',
    usage: 'Shown when action is missing or outside the beginner mapping.',
    impact: [
      'Do not assume the situation is safe—open professional details or wait for a complete decision.',
    ],
  },
  'education.risk.section': {
    title: 'Risks and counter-evidence',
    summary: 'The report layer that lists risks, invalidation ideas, and evidence that challenges the main case.',
    usage: 'Placed after model inference so you see what could go wrong before acting on the conclusion.',
    impact: [
      'Read this section before sizing up; it is meant to slow overconfidence, not to replace full metrics.',
    ],
  },
  'education.risk.gate.pass': {
    title: 'Risk gate: Pass',
    summary: 'The mandatory Risk Manager accepted the proposed final action without changing it.',
    usage: 'Pass only means the gate’s published rules did not force a downgrade or reject for this run.',
    impact: [
      'You may treat the published action as not vetoed by the gate, but you still own position sizing and timing.',
    ],
    notes: [
      'Pass is not a performance forecast and does not remove market risk.',
    ],
  },
  'education.risk.gate.downgrade': {
    title: 'Risk gate: Downgrade',
    summary: 'The Risk Manager softened the original action (for example buy → hold) before publishing.',
    usage: 'Triggered when evidence or profile thresholds require a more cautious final action.',
    impact: [
      'Follow the final action line, not the original more aggressive suggestion.',
    ],
  },
  'education.risk.gate.reject': {
    title: 'Risk gate: Reject',
    summary: 'The Risk Manager blocked publishing the original action as the final recommendation.',
    usage: 'Used when blocking evidence or fail-closed rules prevent the bullish or aggressive action from shipping.',
    impact: [
      'Do not execute the original action; use the final action and reason codes as the system’s published stance.',
    ],
  },
  'education.risk.gate.not_evaluated': {
    title: 'Risk gate: Not evaluated',
    summary: 'No trustworthy Risk Manager conclusion is available for this surface.',
    usage: 'Shown when the payload is missing, malformed, or uses an unsupported schema—never implied as pass.',
    impact: [
      'Assume the gate did not clear the idea; prefer waiting or opening diagnostics rather than treating silence as approval.',
    ],
  },
  'education.risk.gate.error': {
    title: 'Risk gate: Load failed',
    summary: 'The Web client could not read a Risk Manager conclusion for this report or signal.',
    usage: 'Usually a load or parse failure on an otherwise expected payload path.',
    impact: [
      'Retry loading the report; until a verdict appears, do not treat the idea as gate-cleared.',
    ],
  },
  'education.risk.gate.loading': {
    title: 'Risk gate: Loading',
    summary: 'The Risk Manager conclusion is still being fetched for this surface.',
    usage: 'A temporary state while details or metadata arrive.',
    impact: [
      'Wait for pass, downgrade, reject, or not-evaluated before acting on a final action.',
    ],
  },
  'education.portfolio.health': {
    title: 'Portfolio structural health',
    summary: 'How concentrated, volatile, diversified, and cash-balanced the book looks from stored positions and history.',
    usage: 'Portfolio risk views and health scores summarize structure—not whether a single trade will win.',
    impact: [
      'Use weak health or high heatmap cells as a prompt to rebalance size, correlation, or cash—not as a buy/sell order.',
    ],
    notes: [
      'Missing history never pretends to be healthy zero risk; partial states stay explicit.',
    ],
  },
  'education.portfolio.var': {
    title: 'Historical VaR',
    summary: 'Value at Risk estimates how much the portfolio might lose over a short horizon using past returns.',
    usage: 'Computed from stored daily bars only; status not ok keeps VaR null instead of showing fake zero risk.',
    impact: [
      'A larger VaR means historically larger short-horizon loss potential—review size and hedges, not a price target.',
    ],
  },
  'education.portfolio.concentration': {
    title: 'Concentration',
    summary: 'How much portfolio value sits in the largest positions (for example HHI or top weight).',
    usage: 'High concentration means one name or a few names dominate outcomes.',
    impact: [
      'If one holding is very large, consider whether a single adverse move is acceptable for your plan.',
    ],
  },
  'education.portfolio.diversification': {
    title: 'Diversification score',
    summary: 'A structural reading of how spread out effective exposure is across holdings.',
    usage: 'Higher diversification usually means less reliance on a single name; low scores flag crowded books.',
    impact: [
      'Low diversification is a reason to check correlation and size before adding similar risk.',
    ],
  },
  'education.indicator.common': {
    title: 'Technical indicators (MA / MACD / RSI)',
    summary: 'Common trend and momentum tools: moving averages (MA), MACD, and RSI.',
    usage: 'Reports may weight technical signals alongside news and fundamentals; open each indicator’s help where shown for field-level detail.',
    impact: [
      'Use indicators as context for structure and timing, not as standalone trade orders or performance guarantees.',
    ],
    notes: [
      'MA, MACD, and RSI can disagree; risk limits and invalidation still come first.',
    ],
  },
  'education.indicator.ma': {
    title: 'Moving average (MA)',
    summary: 'The average close over N trading days, plotted as a smooth trend line (for example MA5, MA20).',
    usage: 'Price above a rising MA is often read as short-term strength; below a falling MA as weakness—context still matters.',
    impact: [
      'Use MAs as trend context and support/resistance reference, not as standalone buy/sell orders.',
    ],
    notes: [
      'When history is shorter than the period, that MA is omitted rather than faked with a shorter window.',
    ],
  },
  'education.indicator.macd': {
    title: 'MACD',
    summary: 'Moving Average Convergence Divergence compares a fast and slow EMA and a signal line (default 12/26/9).',
    usage: 'Crosses and histogram direction describe momentum shifts; they lag price and can whipsaw in ranges.',
    impact: [
      'Treat golden/death crosses as momentum hints to combine with risk and levels—not as guaranteed entries.',
    ],
  },
  'education.indicator.rsi': {
    title: 'RSI',
    summary: 'Relative Strength Index scales recent gains versus losses on a 0–100 scale (common periods 6/12/24).',
    usage: 'High readings often flag short-term overbought pressure; low readings oversold pressure—thresholds are conventional, not destiny.',
    impact: [
      'Extreme RSI can warn of stretched moves, but trends can stay extended; pair with structure and risk limits.',
    ],
  },

};

export default educationHelpEnUS;
