// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { parseMoneyFlowView } from '../moneyFlow';

const partialPayload = () => ({
  schema_version: 'money_flow_view/1.0',
  stock_code: '600519',
  enabled: true,
  status: 'partial',
  requested_days: 5,
  fetched_at: '2026-08-08T08:01:00Z',
  as_of: '2026-08-08T08:00:00Z',
  provider_date: '2026-08-08',
  age_days: 0,
  source: 'akshare:test',
  source_chain: [{ provider: 'akshare', status: 'success', latency_ms: 12 }],
  market: 'cn',
  error_code: null,
  warnings: ['money_flow_amount_scale_is_not_authoritatively_calibrated'],
  cache_state: 'miss',
  fallback_from: null,
  snapshot: {
    code: '600519',
    date: '2026-08-08',
    source: 'akshare:test',
    market: 'cn',
    main_net_inflow_ratio: 1.5,
    unit: 'unknown',
    amount_scale: 'unknown',
    bucket_definition: 'eastmoney_em_order_size_buckets_v1',
    as_of: '2026-08-08T08:00:00Z',
    requested_days: 5,
    observed_days: 5,
    completeness: 'complete',
    attitude: 'inflow',
    calibration_note: 'Ratios only.',
  },
  message: 'Money-flow data is degraded.',
  disclaimer: 'Research evidence only.',
});

describe('moneyFlow contract', () => {
  it('parses the strict finite cross-stack response', () => {
    const parsed = parseMoneyFlowView(partialPayload());
    expect(parsed.snapshot?.mainNetInflowRatio).toBe(1.5);
    expect(parsed.sourceChain?.[0]?.latencyMs).toBe(12);
  });

  it('rejects non-finite metrics and unknown response fields', () => {
    const nonFinite = partialPayload();
    nonFinite.snapshot.main_net_inflow_ratio = Number.NaN;
    expect(() => parseMoneyFlowView(nonFinite)).toThrow();

    expect(() =>
      parseMoneyFlowView({ ...partialPayload(), uncontracted_debug: 'hidden' }),
    ).toThrow();

    const uncalibratedAmount = partialPayload();
    Object.assign(uncalibratedAmount.snapshot, { main_net_inflow_5d: 1000 });
    expect(() => parseMoneyFlowView(uncalibratedAmount)).toThrow();
  });

  it('rejects a missing or invented status instead of presenting success', () => {
    expect(() => parseMoneyFlowView({ ...partialPayload(), status: 'passed' })).toThrow();
    expect(() =>
      parseMoneyFlowView({ ...partialPayload(), status: 'partial', snapshot: null }),
    ).toThrow();
  });
});
