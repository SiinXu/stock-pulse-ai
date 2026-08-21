// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { getParsedApiError } from '../error';
import { onboardingApi } from '../onboarding';
import { DEFAULT_ONBOARDING_PROFILE } from '../../types/onboarding';

vi.mock('../index', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

const get = vi.mocked(apiClient.get);
const post = vi.mocked(apiClient.post);
const del = vi.mocked(apiClient.delete);

function expectValidationFailed(error: unknown): boolean {
  expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
  return true;
}

const requiredPlan = {
  schema_version: 1,
  engine: 'rules',
  llm_note: 'Rule-based plan (default).',
  profile: {
    schema_version: 1,
    experience_stage: 'beginner',
    markets: ['cn'],
    goals: ['pre_post_market'],
    holdings: 'none',
    interaction: 'web',
    risk_tone: 'balanced',
    infrastructure: 'cloud_key',
    report_language: 'en',
  },
  feature_stage: 'L0',
  feature_path: {
    stage: 'L0',
    label: 'Cold start',
    primary_path: ['Configure model'],
    emphasize: ['home'],
    defer: ['committee'],
  },
  recommended_preset_id: 'cloud-balanced',
  recommended_preset_name: 'Cloud balanced',
  disclaimer: 'Never places buy/sell orders and never invents API keys.',
  generated_at: '2026-08-06T00:00:00Z',
};

const fullPlan = {
  ...requiredPlan,
  model_available: false,
  prefer_llm: false,
  beginner_mode_recommended: true,
  config_changes: [{ key: 'REPORT_LANGUAGE', from: '', to: 'en' }],
  config_items: [{ key: 'REPORT_LANGUAGE', value: 'en' }],
  todos: [{
    id: 'paste_cloud_key',
    priority: 1,
    title: 'Paste a cloud provider API key',
    description: 'Never invent keys.',
    href: '/settings',
    kind: 'secret_guide',
  }],
  today_plan: [{
    id: 'step_analyze',
    title: 'Analyze one watchlist symbol',
    detail: 'Open Analysis Workbench.',
  }],
  week_plan: [{ day: '2', title: 'Compare with history', detail: 'Review.' }],
};

const expectedFullPlanCamel = {
  schemaVersion: 1,
  engine: 'rules',
  llmNote: 'Rule-based plan (default).',
  profile: {
    schemaVersion: 1,
    experienceStage: 'beginner',
    markets: ['cn'],
    goals: ['pre_post_market'],
    holdings: 'none',
    interaction: 'web',
    riskTone: 'balanced',
    infrastructure: 'cloud_key',
    reportLanguage: 'en',
  },
  featureStage: 'L0',
  featurePath: {
    stage: 'L0',
    label: 'Cold start',
    primaryPath: ['Configure model'],
    emphasize: ['home'],
    defer: ['committee'],
  },
  recommendedPresetId: 'cloud-balanced',
  recommendedPresetName: 'Cloud balanced',
  disclaimer: 'Never places buy/sell orders and never invents API keys.',
  generatedAt: '2026-08-06T00:00:00Z',
  modelAvailable: false,
  preferLlm: false,
  beginnerModeRecommended: true,
  configChanges: [{ key: 'REPORT_LANGUAGE', from: '', to: 'en' }],
  configItems: [{ key: 'REPORT_LANGUAGE', value: 'en' }],
  todos: [{
    id: 'paste_cloud_key',
    priority: 1,
    title: 'Paste a cloud provider API key',
    description: 'Never invent keys.',
    href: '/settings',
    kind: 'secret_guide',
  }],
  todayPlan: [{
    id: 'step_analyze',
    title: 'Analyze one watchlist symbol',
    detail: 'Open Analysis Workbench.',
  }],
  weekPlan: [{ day: '2', title: 'Compare with history', detail: 'Review.' }],
};

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
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

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

describe('onboarding plan/apply/state/reset response contracts', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it('posts snake_case plan requests and returns byte-equivalent camelCase payloads', async () => {
    post.mockResolvedValueOnce({ data: fullPlan });
    const result = await onboardingApi.generatePlan({
      profile: DEFAULT_ONBOARDING_PROFILE,
      modelAvailable: false,
      preferLlm: false,
    });
    expect(post).toHaveBeenCalledWith('/api/v1/onboarding/plan', {
      profile: {
        schema_version: 1,
        experience_stage: 'beginner',
        markets: ['cn'],
        goals: ['pre_post_market'],
        holdings: 'none',
        interaction: 'web',
        risk_tone: 'balanced',
        infrastructure: 'cloud_key',
        report_language: 'zh',
      },
      model_available: false,
      prefer_llm: false,
    });
    expect(result).toEqual(expectedFullPlanCamel);
  });

  it('preserves extra root and nested feature_path keys on valid plan payloads', async () => {
    post.mockResolvedValueOnce({
      data: {
        ...fullPlan,
        extra_debug_flag: 'keep-me',
        feature_path: { ...fullPlan.feature_path, extra_tag: 'x' },
      },
    });
    const result = await onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE });
    expect(result).toEqual({
      ...expectedFullPlanCamel,
      extraDebugFlag: 'keep-me',
      featurePath: { ...expectedFullPlanCamel.featurePath, extraTag: 'x' },
    });
  });

  it('defaults omitted plan collections to empty arrays after a successful parse', async () => {
    post.mockResolvedValueOnce({ data: requiredPlan });
    const result = await onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE });
    expect(result.configChanges).toEqual([]);
    expect(result.configItems).toEqual([]);
    expect(result.todos).toEqual([]);
    expect(result.todayPlan).toEqual([]);
    expect(result.weekPlan).toEqual([]);
    expect(result.engine).toBe('rules');
    expect(result.featurePath.stage).toBe('L0');
  });

  it('rejects a plan payload missing engine', async () => {
    const { engine: _engine, ...withoutEngine } = requiredPlan;
    void _engine;
    post.mockResolvedValueOnce({ data: withoutEngine });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
  });

  it('rejects a plan payload whose feature_path is missing stage', async () => {
    post.mockResolvedValueOnce({
      data: { ...requiredPlan, feature_path: { label: 'Cold start' } },
    });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
  });

  it('rejects a plan payload whose feature_path is not an object', async () => {
    post.mockResolvedValueOnce({ data: { ...requiredPlan, feature_path: 'L0' } });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
  });

  it('rejects NaN and Infinity schema_version values', async () => {
    post.mockResolvedValueOnce({ data: { ...requiredPlan, schema_version: Number.NaN } });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
    post.mockResolvedValueOnce({ data: { ...requiredPlan, schema_version: Number.POSITIVE_INFINITY } });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
    post.mockResolvedValueOnce({ data: { ...requiredPlan, schema_version: Number.NEGATIVE_INFINITY } });
    await expect(onboardingApi.generatePlan({ profile: DEFAULT_ONBOARDING_PROFILE }))
      .rejects.toSatisfy(expectValidationFailed);
  });

  it('preserves extra apply keys and nested plan fields', async () => {
    post.mockResolvedValueOnce({
      data: {
        success: true,
        config_version: 'v2',
        applied_keys: ['REPORT_LANGUAGE'],
        applied_count: 1,
        plan: { ...fullPlan, extra_plan_flag: 'keep-plan' },
        profile: fullPlan.profile,
        message: 'ok',
        trace_id: 'abc',
      },
    });
    const result = await onboardingApi.applyPlan({
      profile: DEFAULT_ONBOARDING_PROFILE,
      configVersion: 'v1',
      confirm: true,
    });
    expect(post).toHaveBeenCalledWith('/api/v1/onboarding/apply', expect.objectContaining({
      config_version: 'v1',
      confirm: true,
      model_available: false,
      prefer_llm: false,
    }));
    expect(result.success).toBe(true);
    expect(result).toEqual(expect.objectContaining({
      success: true,
      configVersion: 'v2',
      appliedKeys: ['REPORT_LANGUAGE'],
      appliedCount: 1,
      message: 'ok',
      traceId: 'abc',
    }));
    expect(result.plan).toEqual({ ...expectedFullPlanCamel, extraPlanFlag: 'keep-plan' });
  });

  it('rejects apply payloads whose nested plan is missing recommended_preset_id', async () => {
    const { recommended_preset_id: _id, ...planWithoutPreset } = requiredPlan;
    void _id;
    post.mockResolvedValueOnce({
      data: {
        success: true,
        config_version: 'v2',
        plan: planWithoutPreset,
        profile: requiredPlan.profile,
        message: 'ok',
      },
    });
    await expect(onboardingApi.applyPlan({
      profile: DEFAULT_ONBOARDING_PROFILE,
      configVersion: 'v1',
    })).rejects.toSatisfy(expectValidationFailed);
  });

  it('defaults omitted apply and state applied_keys to empty arrays', async () => {
    post.mockResolvedValueOnce({
      data: {
        success: true,
        config_version: 'v2',
        plan: requiredPlan,
        profile: requiredPlan.profile,
        message: 'ok',
      },
    });
    const applied = await onboardingApi.applyPlan({
      profile: DEFAULT_ONBOARDING_PROFILE,
      configVersion: 'v1',
    });
    expect(applied.appliedKeys).toEqual([]);
    expect(applied.plan.todayPlan).toEqual([]);

    get.mockResolvedValueOnce({
      data: { exists: true, plan: requiredPlan, profile: requiredPlan.profile },
    });
    const state = await onboardingApi.getState();
    expect(state.exists).toBe(true);
    expect(state.appliedKeys).toEqual([]);
    expect(state.plan?.todayPlan).toEqual([]);
  });

  it('rejects state payloads whose exists field is not a boolean', async () => {
    get.mockResolvedValueOnce({ data: { exists: 'yes' } });
    await expect(onboardingApi.getState()).rejects.toSatisfy(expectValidationFailed);
  });

  it('returns a valid reset payload and rejects a numeric reset flag', async () => {
    del.mockResolvedValueOnce({ data: { success: true, reset: true, message: 'cleared' } });
    const result = await onboardingApi.resetState();
    expect(del).toHaveBeenCalledWith('/api/v1/onboarding/state');
    expect(result).toEqual({ success: true, reset: true, message: 'cleared' });

    del.mockResolvedValueOnce({ data: { success: true, reset: 1, message: 'cleared' } });
    await expect(onboardingApi.resetState()).rejects.toSatisfy(expectValidationFailed);
  });
});
