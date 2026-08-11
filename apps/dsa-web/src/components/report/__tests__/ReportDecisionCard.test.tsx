// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportDecisionCard } from '../ReportDecisionCard';
import {
  buildReportDecisionCardModel,
  hasReportDecisionCardContent,
} from '../reportDecisionCardUtils';
import type { ReportDetails, ReportMeta, ReportSummary } from '../../../types/analysis';

const baseMeta: ReportMeta = {
  queryId: 'q-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  reportType: 'detailed',
  reportLanguage: 'zh',
  createdAt: '2026-03-21T08:00:00Z',
};

const baseSummary: ReportSummary = {
  analysisSummary: '趋势维持强势',
  operationAdvice: '继续观察买点',
  action: 'hold',
  trendPrediction: '短线震荡偏强',
  sentimentScore: 78,
};

describe('reportDecisionCardUtils', () => {
  it('assembles fields from dashboard + projected summary like the Jinja Decision Card', () => {
    const details: ReportDetails = {
      rawResult: {
        confidence_level: '高',
        risk_warning: 'fallback warning',
        dashboard: {
          core_conclusion: {
            one_sentence: '等待放量确认',
            time_sensitivity: '今日内',
            position_advice: {
              no_position: '观望',
              has_position: '继续持有',
            },
          },
          intelligence: { risk_alerts: ['业绩不及预期', '板块轮动风险'] },
          phase_decision: {
            immediate_action: '等待确认',
            watch_conditions: ['放量突破', '跌破支撑离场'],
            confidence_reason: '数据质量可用',
          },
          battle_plan: {
            sniper_points: { stop_loss: '110', take_profit: '130' },
          },
        },
      },
    };

    const model = buildReportDecisionCardModel({
      meta: baseMeta,
      summary: baseSummary,
      details,
      signalLabel: '持有',
    });

    expect(model.oneSentence).toBe('等待放量确认');
    expect(model.confidenceLevel).toBe('高');
    expect(model.keyRisks).toEqual(['业绩不及预期', '板块轮动风险']);
    expect(model.riskWarning).toBeUndefined();
    expect(model.watchConditions).toEqual(['放量突破', '跌破支撑离场']);
    expect(model.stopLoss).toBe('110');
    expect(model.takeProfit).toBe('130');
    expect(model.positionNoPosition).toBe('观望');
    expect(hasReportDecisionCardContent(model)).toBe(true);
  });

  it('degrades without empty optional fields when dashboard is absent', () => {
    const model = buildReportDecisionCardModel({
      meta: baseMeta,
      summary: {
        analysisSummary: '仅有摘要',
        operationAdvice: '',
        trendPrediction: '',
        sentimentScore: 50,
      },
      details: { rawResult: {} },
    });

    expect(model.oneSentence).toBe('仅有摘要');
    expect(model.keyRisks).toEqual([]);
    expect(model.watchConditions).toEqual([]);
    expect(model.confidenceLevel).toBeUndefined();
    expect(model.riskWarning).toBeUndefined();
    expect(model.stopLoss).toBeUndefined();
  });

  it('uses risk_warning when risk_alerts are missing', () => {
    const model = buildReportDecisionCardModel({
      meta: baseMeta,
      summary: baseSummary,
      details: {
        rawResult: {
          risk_warning: '流动性风险',
          dashboard: {
            core_conclusion: { one_sentence: '谨慎持有' },
            intelligence: {},
          },
        },
      },
    });

    expect(model.keyRisks).toEqual([]);
    expect(model.riskWarning).toBe('流动性风险');
  });
});

describe('ReportDecisionCard', () => {
  it('renders decision fields and omits empty optional rows', () => {
    render(
      <ReportDecisionCard
        meta={baseMeta}
        summary={baseSummary}
        details={{
          rawResult: {
            confidence_level: '高',
            dashboard: {
              core_conclusion: { one_sentence: '等待放量确认' },
              intelligence: { risk_alerts: ['业绩不及预期'] },
              phase_decision: { watch_conditions: ['放量突破'] },
            },
          },
        }}
      />,
    );

    const card = screen.getByTestId('report-decision-card');
    expect(card).toBeVisible();
    expect(screen.getByText('决策卡')).toBeVisible();
    expect(screen.getByText('等待放量确认')).toBeVisible();
    expect(screen.getByText('高')).toBeVisible();
    expect(screen.getByTestId('report-decision-card-risks')).toHaveTextContent('业绩不及预期');
    expect(screen.getByTestId('report-decision-card-watch')).toHaveTextContent('放量突破');
    expect(screen.queryByText('风险提示')).not.toBeInTheDocument();
    expect(screen.queryByText('操作点位')).not.toBeInTheDocument();
  });

  it('returns null when there is no decision content', () => {
    const { container } = render(
      <ReportDecisionCard
        meta={baseMeta}
        summary={{
          analysisSummary: '',
          operationAdvice: '',
          trendPrediction: '',
          sentimentScore: Number.NaN,
        }}
        details={{}}
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('report-decision-card')).not.toBeInTheDocument();
  });
});
