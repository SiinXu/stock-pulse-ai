// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MoneyFlowView } from '../../../api/moneyFlow';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { MoneyFlowPanel } from '../MoneyFlowPanel';

const disabledView: MoneyFlowView = {
  schemaVersion: 'money_flow_view/1.0',
  stockCode: '600519',
  enabled: false,
  status: 'disabled',
  requestedDays: 5,
  disclaimer: 'Research evidence only.',
  message: 'SmartMoney money-flow is disabled.',
  warnings: [],
  sourceChain: [],
};

const partialView: MoneyFlowView = {
  schemaVersion: 'money_flow_view/1.0',
  stockCode: '600519',
  enabled: true,
  status: 'partial',
  requestedDays: 5,
  asOf: '2026-08-08T08:00:00+00:00',
  providerDate: '2026-08-08',
  ageDays: 0,
  source: 'akshare:stock_individual_fund_flow',
  message: 'Money-flow data is degraded (status=partial).',
  warnings: ['money_flow_amount_scale_is_not_authoritatively_calibrated'],
  sourceChain: [{ provider: 'akshare', status: 'partial' }],
  disclaimer: 'Research evidence only.',
  snapshot: {
    code: '600519',
    date: '2026-08-08',
    source: 'akshare:stock_individual_fund_flow',
    mainNetInflowRatio: 1.5,
    superLargeNetInflowRatio: 0.8,
    largeNetInflowRatio: 0.7,
    mediumNetInflowRatio: -0.3,
    smallNetInflowRatio: -1.2,
    unit: 'unknown',
    amountScale: 'unknown',
    bucketDefinition: 'eastmoney_em_order_size_buckets_v1',
    completeness: 'complete',
    observedDays: 5,
    requestedDays: 5,
    attitude: 'inflow',
    calibrationNote: 'Order-size buckets follow bucket_definition.',
  },
};

const renderPanel = (ui: ReactElement) =>
  render(<UiLanguageProvider initialLanguage="en">{ui}</UiLanguageProvider>);

describe('MoneyFlowPanel', () => {
  it('renders disabled gate without inventing bucket numbers', () => {
    renderPanel(<MoneyFlowPanel stockCode="600519" initialView={disabledView} />);
    expect(screen.getByTestId('money-flow-panel')).toBeInTheDocument();
    expect(screen.getByTestId('money-flow-disabled')).toBeInTheDocument();
    expect(screen.getByTestId('money-flow-status')).toHaveTextContent('disabled');
    expect(screen.queryByTestId('money-flow-snapshot')).not.toBeInTheDocument();
    expect(screen.getByTestId('money-flow-disclaimer')).toHaveTextContent(/Research evidence/i);
  });

  it('renders as-of, source, ratios, and degraded warning for partial data', () => {
    renderPanel(<MoneyFlowPanel stockCode="600519" initialView={partialView} />);
    expect(screen.getByTestId('money-flow-degraded')).toBeInTheDocument();
    expect(screen.getByTestId('money-flow-source')).toHaveTextContent('akshare:stock_individual_fund_flow');
    expect(screen.getByTestId('money-flow-as-of')).toHaveTextContent('2026-08-08T08:00:00+00:00');
    expect(screen.getByTestId('money-flow-provider-date')).toHaveTextContent('2026-08-08');
    expect(screen.getByTestId('money-flow-main-ratio')).toHaveTextContent('+1.50%');
    expect(screen.getByTestId('money-flow-attitude')).toHaveTextContent(/Inflow/i);
    expect(screen.getByTestId('money-flow-warnings')).toHaveTextContent(
      'money_flow_amount_scale_is_not_authoritatively_calibrated',
    );
    expect(screen.getByTestId('money-flow-bucket')).toHaveTextContent('eastmoney_em_order_size_buckets_v1');
  });

  it('loads via fetchView and exposes refresh control (reachability)', async () => {
    const fetchView = vi
      .fn()
      .mockResolvedValueOnce(disabledView)
      .mockResolvedValueOnce(partialView);
    renderPanel(<MoneyFlowPanel stockCode="600519" fetchView={fetchView} />);
    await waitFor(() => {
      expect(screen.getByTestId('money-flow-disabled')).toBeInTheDocument();
    });
    expect(fetchView).toHaveBeenCalledWith('600519', 5);
    fireEvent.click(screen.getByTestId('money-flow-refresh'));
    await waitFor(() => {
      expect(screen.getByTestId('money-flow-snapshot')).toBeInTheDocument();
    });
    expect(fetchView).toHaveBeenCalledTimes(2);
  });

  it('ignores stale slower responses after a newer refresh', async () => {
    let resolveSlow: ((value: MoneyFlowView) => void) | undefined;
    const slowDisabled = new Promise<MoneyFlowView>((resolve) => {
      resolveSlow = resolve;
    });
    let callCount = 0;
    const fetchView = vi.fn(async () => {
      callCount += 1;
      // First in-flight call is deliberately slow; every later call is partial.
      if (callCount === 1) return slowDisabled;
      return partialView;
    });

    renderPanel(<MoneyFlowPanel stockCode="600519" fetchView={fetchView} />);
    await waitFor(() => expect(fetchView).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('money-flow-refresh'));
    await waitFor(() => {
      expect(screen.getByTestId('money-flow-snapshot')).toBeInTheDocument();
    });
    expect(screen.getByTestId('money-flow-main-ratio')).toHaveTextContent('+1.50%');

    // Late disabled payload must not overwrite the newer partial snapshot.
    resolveSlow?.(disabledView);
    await Promise.resolve();
    expect(screen.getByTestId('money-flow-snapshot')).toBeInTheDocument();
    expect(screen.queryByTestId('money-flow-disabled')).not.toBeInTheDocument();
    expect(screen.getByTestId('money-flow-status')).toHaveTextContent('partial');
  });
});
