// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { getParsedApiError } from '../error';
import { onboardingApi } from '../onboarding';

vi.mock('../index', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

const get = vi.mocked(apiClient.get);

const validReadiness = {
  schema_version: 1,
  is_fresh_environment: true,
  has_primary_model: false,
  beginner_mode_recommended: true,
  primary_path: 'demo',
  primary_cta: 'view_demo',
  reason_code: 'local_runtime_no_models',
  reason_params: {},
  local_runtime: {
    reachable: true,
    models_available: false,
    runnable: false,
    backend: 'ollama',
    base_url: 'http://127.0.0.1:11434',
    models: [],
    suggested_profile: {},
    reason_code: 'ollama_no_models',
    detect_enabled: true,
  },
  recommended_preset_id: null,
  suggested_profile: {},
  demo_available: true,
  config_mutated: false,
  existing_config_untouched: true,
  snapshot_id: '0123456789abcdef01234567',
  generated_at: '2026-08-09T00:00:00Z',
};

const validDemo = {
  schema_version: 1,
  is_sample: true,
  sample_banner: 'Sample data — not a live analysis',
  sample_disclaimer: 'Offline fixture only.',
  query_id: 'demo-sample-analysis-v1',
  stock_code: '600519',
  stock_name: 'Kweichow Moutai (sample)',
  created_at: '2026-08-09T00:00:00Z',
  report: {
    meta: {
      query_id: 'demo-sample-analysis-v1',
      stock_code: '600519',
      stock_name: 'Kweichow Moutai (sample)',
      report_type: 'brief',
      report_language: 'en',
      created_at: '2026-08-09T00:00:00Z',
      current_price: null,
      change_pct: null,
      model_used: 'demo-fixture/offline',
    },
    summary: {
      analysis_summary: 'Sample only.',
      operation_advice: 'Configure a real model.',
      action: 'watch',
      action_label: 'Watch (sample)',
      trend_prediction: 'Not live.',
      sentiment_score: 50,
      sentiment_label: 'Neutral',
    },
    strategy: { ideal_buy: null, secondary_buy: null, stop_loss: null, take_profit: null },
    details: { news: [], technical: [] },
  },
};

describe('onboarding first-run response contracts', () => {
  beforeEach(() => get.mockReset());

  it('accepts the bounded readiness snapshot and preserves camelCase payload fields', async () => {
    get.mockResolvedValueOnce({ data: validReadiness });
    const result = await onboardingApi.getFirstRunReadiness();
    expect(result.reasonCode).toBe('local_runtime_no_models');
    expect(result.localRuntime.runnable).toBe(false);
    expect(result.snapshotId).toBe('0123456789abcdef01234567');
  });

  it('rejects an unknown readiness path at the API boundary', async () => {
    get.mockResolvedValueOnce({ data: { ...validReadiness, primary_path: 'magic_fallback' } });
    await expect(onboardingApi.getFirstRunReadiness()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });

  it('requires the demo marker to be the literal true value', async () => {
    get.mockResolvedValueOnce({ data: { ...validDemo, is_sample: false } });
    await expect(onboardingApi.getDemoAnalysis('en')).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
