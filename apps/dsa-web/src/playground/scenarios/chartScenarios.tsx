/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { KlineChart } from '../../components/charts/KlineChart';
import { RiskHeatmap, type RiskHeatmapCell } from '../../components/charts/RiskHeatmap';
import type { StockHistoryCandle } from '../../types/stocks';
import type { PlaygroundScenarioRenderer } from '../types';
import { usePlaygroundScenario } from '../scenarioContext';

function buildDemoCandles(count: number): StockHistoryCandle[] {
  const candles: StockHistoryCandle[] = [];
  let close = 100;
  for (let index = 0; index < count; index += 1) {
    const open = close;
    const drift = Math.sin(index / 3) * 2.2 + (index % 5 === 0 ? -1.5 : 0.8);
    close = Math.max(40, open + drift);
    candles.push({
      date: `2026-01-${String((index % 28) + 1).padStart(2, '0')}`,
      open: Number(open.toFixed(2)),
      high: Number((Math.max(open, close) + 1.2).toFixed(2)),
      low: Number((Math.min(open, close) - 1.1).toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: 800_000 + index * 12_500,
    });
  }
  return candles;
}
const DEMO = buildDemoCandles(36);
const RISK: RiskHeatmapCell[] = [
  { rowId: '600519', rowLabel: '600519', columnId: 'vol', columnLabel: 'Volatility', score: 28 },
  { rowId: '600519', rowLabel: '600519', columnId: 'drawdown', columnLabel: 'Drawdown', score: 41 },
  { rowId: 'AAPL', rowLabel: 'AAPL', columnId: 'vol', columnLabel: 'Volatility', score: 35 },
  { rowId: 'AAPL', rowLabel: 'AAPL', columnId: 'drawdown', columnLabel: 'Drawdown', score: 29 },
  { rowId: 'TSLA', rowLabel: 'TSLA', columnId: 'vol', columnLabel: 'Volatility', score: 88 },
  { rowId: 'TSLA', rowLabel: 'TSLA', columnId: 'drawdown', columnLabel: 'Drawdown', score: Number.NaN },
];
const KlineChartStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'empty') return <KlineChart candles={[]} />;
  if (scenario === 'states') {
    return <KlineChart candles={[...DEMO.slice(0, 8), { date: '2026-02-01', open: Number.NaN, high: 1, low: 1, close: 1, volume: 1 }]} market="cn" />;
  }
  return <KlineChart candles={DEMO} market="cn" height={360} />;
};
const RiskHeatmapStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <RiskHeatmap cells={scenario === 'empty' ? [] : RISK} />;
};
export const CHART_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'kline-chart': KlineChartStory,
  'risk-heatmap': RiskHeatmapStory,
};
