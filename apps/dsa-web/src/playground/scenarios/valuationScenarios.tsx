/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { DcfSensitivityPanel, PeerValuationCanvas } from '../../components/valuation';
import type { PeerValuationCanvas as PeerCanvasPayload, ValuationEstimate } from '../../api/valuation';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const SAMPLE_ESTIMATE: ValuationEstimate = {
  schemaVersion: 'valuation-estimate-v1',
  status: 'ok',
  stockCode: 'AAPL',
  dcf: {
    status: 'ok',
    equityValue: 1446.21,
    intrinsicValuePerShare: 14.46,
    assumptions: {
      growthRate: 0.05,
      discountRate: 0.1,
      terminalGrowthRate: 0.02,
      projectionYears: 5,
      cashFlowSource: 'operating_cash_flow',
      growthSource: 'caller_override',
    },
    sensitivity: {
      rows: [
        { growthRate: 0.03, discountRate: 0.09, equityValue: 1600 },
        { growthRate: 0.05, discountRate: 0.09, equityValue: 1700 },
        { growthRate: 0.07, discountRate: 0.09, equityValue: 1800 },
        { growthRate: 0.03, discountRate: 0.1, equityValue: 1400 },
        { growthRate: 0.05, discountRate: 0.1, equityValue: 1446.21 },
        { growthRate: 0.07, discountRate: 0.1, equityValue: 1500 },
        { growthRate: 0.03, discountRate: 0.11, equityValue: 1200 },
        { growthRate: 0.05, discountRate: 0.11, equityValue: 1300 },
        { growthRate: 0.07, discountRate: 0.11, equityValue: 1350 },
      ],
      equityValueLow: 1200,
      equityValueMid: 1446.21,
      equityValueHigh: 1800,
    },
  },
  relative: { status: 'ok' },
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const EMPTY_ESTIMATE: ValuationEstimate = {
  schemaVersion: 'valuation-estimate-v1',
  status: 'insufficient_fundamentals',
  stockCode: 'EMPTY',
  dcf: {
    status: 'insufficient_fundamentals',
    message: 'Insufficient fundamentals for DCF',
    assumptions: { growthRate: 0.05, discountRate: 0.1, terminalGrowthRate: 0.03, projectionYears: 5 },
    sensitivity: { rows: [], equityValueLow: null, equityValueMid: null, equityValueHigh: null },
  },
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const SAMPLE_PEER_CANVAS: PeerCanvasPayload = {
  schemaVersion: 'peer-valuation-canvas-v1',
  status: 'partial',
  stockCode: '600519',
  baseCurrency: 'CNY',
  fxStale: false,
  peerSet: {
    source: 'custom',
    sourceLabel: 'Manual peer set',
    explanation: 'Caller-supplied peer codes; membership is not inferred.',
  },
  metrics: ['peRatio', 'pbRatio', 'marketCap'],
  rows: [
    {
      stockCode: '600519',
      role: 'target',
      dataStatus: 'ok',
      missingMetrics: [],
      metrics: {
        peRatio: { value: 30, status: 'ok' },
        pbRatio: { value: 8, status: 'ok' },
        marketCap: { value: 2_000_000, status: 'ok', currency: 'CNY' },
        currentPrice: { value: 1_600, status: 'ok', currency: 'CNY' },
      },
    },
    {
      stockCode: '000858',
      role: 'peer',
      dataStatus: 'partial',
      missingMetrics: ['pbRatio'],
      metrics: {
        peRatio: { value: 20, status: 'ok' },
        pbRatio: { value: null, status: 'missing', missingReason: 'unavailable' },
        marketCap: { value: 800_000, status: 'ok', currency: 'CNY' },
        currentPrice: { value: 120, status: 'ok', currency: 'CNY' },
      },
    },
  ],
  medians: { peMedian: 20, pbMedian: 8 },
  heatmapCells: [
    { rowId: '600519', rowLabel: '600519', columnId: 'pe_ratio', columnLabel: 'P/E', score: 60 },
    { rowId: '000858', rowLabel: '000858', columnId: 'pe_ratio', columnLabel: 'P/E', score: 40 },
  ],
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const DcfSensitivityPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'empty') {
    return <div className="max-w-3xl"><DcfSensitivityPanel estimate={EMPTY_ESTIMATE} stockCode="EMPTY" readOnly /></div>;
  }
  if (scenario === 'interactive') {
    return (
      <div className="max-w-3xl">
        <DcfSensitivityPanel
          estimate={SAMPLE_ESTIMATE}
          stockCode="AAPL"
          fetchEstimate={async (params) => ({
            ...SAMPLE_ESTIMATE,
            stockCode: params.stockCode,
            dcf: {
              ...SAMPLE_ESTIMATE.dcf,
              equityValue: 1500 + (params.growthRate ?? 0.05) * 1000,
              assumptions: {
                growthRate: params.growthRate ?? 0.05,
                discountRate: params.discountRate ?? 0.1,
                terminalGrowthRate: params.terminalGrowthRate ?? 0.02,
                projectionYears: params.projectionYears ?? 5,
              },
            },
          })}
        />
      </div>
    );
  }
  return <div className="max-w-3xl"><DcfSensitivityPanel estimate={SAMPLE_ESTIMATE} stockCode="AAPL" readOnly /></div>;
};

const PeerValuationCanvasStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'empty') {
    return <div className="max-w-5xl"><PeerValuationCanvas stockCode="600519" readOnly /></div>;
  }
  if (scenario === 'interactive') {
    return (
      <div className="max-w-5xl">
        <PeerValuationCanvas
          stockCode="600519"
          fetchCanvas={async () => SAMPLE_PEER_CANVAS}
        />
      </div>
    );
  }
  return (
    <div className="max-w-5xl">
      <PeerValuationCanvas canvas={SAMPLE_PEER_CANVAS} stockCode="600519" readOnly />
    </div>
  );
};

export const VALUATION_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'dcf-sensitivity-panel': DcfSensitivityPanelStory,
  'peer-valuation-canvas': PeerValuationCanvasStory,
};
