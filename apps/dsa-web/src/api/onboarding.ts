// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { getParsedApiError } from './error';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type {
  DemoAnalysisPayload,
  FirstRunReadiness,
  OnboardingApplyResult,
  OnboardingFeaturePath,
  OnboardingPlan,
  OnboardingState,
  UserOnboardingProfile,
} from '../types/onboarding';

const BASE_PATH = '/api/v1/onboarding';
import type { components } from '../types/api.generated';
type OpenApiOnboardingState = components['schemas']['OnboardingStateResponse'];
type OpenApiOnboardingPlan = components['schemas']['OnboardingPlanResponse'];
type OpenApiOnboardingApply = components['schemas']['OnboardingApplyResponse'];
type OpenApiOnboardingReset = components['schemas']['OnboardingResetResponse'];
type OpenApiFirstRun = components['schemas']['FirstRunReadinessResponse'];
type OpenApiDemo = components['schemas']['DemoAnalysisResponse'];
type _AssertState = keyof OpenApiOnboardingState;
type _AssertPlan = keyof OpenApiOnboardingPlan;
type _AssertApply = keyof OpenApiOnboardingApply;
type _AssertReset = keyof OpenApiOnboardingReset;
type _AssertFirstRun = keyof OpenApiFirstRun;
type _AssertDemo = keyof OpenApiDemo;
const _stateAnchor: _AssertState = 'exists';
const _planAnchor: _AssertPlan = 'week_plan';
const _applyAnchor: _AssertApply = 'applied_keys';
const _resetAnchor: _AssertReset = 'reset';
const _firstRunAnchor: _AssertFirstRun = 'primary_path';
const _demoAnchor: _AssertDemo = 'is_sample';
void _stateAnchor;
void _planAnchor;
void _applyAnchor;
void _resetAnchor;
void _firstRunAnchor;
void _demoAnchor;


const reportLanguageSchema = z.enum(['zh', 'en', 'ko']);
const stringRecordSchema = z.record(z.string(), z.string());
const firstRunReadinessSchema = z.object({
  schemaVersion: z.literal(1),
  isFreshEnvironment: z.boolean(),
  hasPrimaryModel: z.boolean(),
  beginnerModeRecommended: z.boolean(),
  primaryPath: z.enum(['configured', 'local_ollama', 'demo']),
  primaryCta: z.enum(['continue', 'open_local_setup', 'view_demo']),
  reasonCode: z.enum([
    'primary_model_configured',
    'local_model_ready',
    'local_runtime_no_models',
    'local_detect_disabled',
    'local_runtime_unavailable',
  ]),
  reasonParams: stringRecordSchema,
  localRuntime: z.object({
    reachable: z.boolean(),
    modelsAvailable: z.boolean(),
    runnable: z.boolean(),
    backend: z.literal('ollama').nullable().optional(),
    baseUrl: z.string().max(512).nullable().optional(),
    models: z.array(z.string()).max(8),
    suggestedProfile: stringRecordSchema,
    reasonCode: z.enum(['ollama_ready', 'ollama_no_models', 'detect_disabled', 'ollama_unreachable']),
    detectEnabled: z.boolean(),
  }),
  recommendedPresetId: z.literal('local-first').nullable().optional(),
  suggestedProfile: stringRecordSchema,
  demoAvailable: z.literal(true),
  configMutated: z.literal(false),
  existingConfigUntouched: z.literal(true),
  snapshotId: z.string().regex(/^[0-9a-f]{24}$/u),
  generatedAt: z.string().datetime({ offset: true }),
});

const demoAnalysisSchema = z.object({
  schemaVersion: z.literal(1),
  isSample: z.literal(true),
  sampleBanner: z.string().min(1).max(240),
  sampleDisclaimer: z.string().min(1).max(800),
  queryId: z.literal('demo-sample-analysis-v1'),
  stockCode: z.literal('600519'),
  stockName: z.string().min(1).max(120),
  createdAt: z.string().datetime({ offset: true }),
  report: z.object({
    meta: z.object({
      queryId: z.literal('demo-sample-analysis-v1'),
      stockCode: z.literal('600519'),
      stockName: z.string().min(1).max(120),
      reportType: z.literal('brief'),
      reportLanguage: reportLanguageSchema,
      createdAt: z.string().datetime({ offset: true }),
      currentPrice: z.null(),
      changePct: z.null(),
      modelUsed: z.literal('demo-fixture/offline'),
    }),
    summary: z.object({
      analysisSummary: z.string().min(1).max(1200),
      operationAdvice: z.string().min(1).max(800),
      action: z.literal('watch'),
      actionLabel: z.string().min(1).max(120),
      trendPrediction: z.string().min(1).max(240),
      sentimentScore: z.number().int().min(0).max(100),
      sentimentLabel: z.enum(['中性', 'Neutral', '중립']),
    }),
    strategy: z.object({
      idealBuy: z.null(),
      secondaryBuy: z.null(),
      stopLoss: z.null(),
      takeProfit: z.null(),
    }),
    details: z.object({
      news: z.array(z.string()).max(0),
      technical: z.array(z.string()).max(0),
    }),
  }),
});

const finiteNumber = z.number().finite();
const stringListSchema = z.array(z.string());
const objectRecordSchema = z.record(z.string(), z.unknown());

const onboardingFeaturePathSchema = z.object({
  stage: z.string(),
  label: z.string(),
  primaryPath: stringListSchema.optional(),
  emphasize: stringListSchema.optional(),
  defer: stringListSchema.optional(),
}).passthrough();

const onboardingConfigItemSchema = z.object({
  key: z.string(),
  value: z.string(),
}).passthrough();

const onboardingTodoItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  priority: finiteNumber.optional(),
  href: z.string().nullable().optional(),
  kind: z.string().optional(),
}).passthrough();

const onboardingPlanStepSchema = z.object({
  id: z.string(),
  title: z.string(),
  detail: z.string(),
}).passthrough();

const onboardingWeekStepSchema = z.object({
  day: z.string(),
  title: z.string(),
  detail: z.string(),
}).passthrough();

const onboardingPlanSchema = z.object({
  schemaVersion: finiteNumber,
  engine: z.string(),
  llmNote: z.string(),
  profile: objectRecordSchema,
  featureStage: z.string(),
  featurePath: onboardingFeaturePathSchema,
  recommendedPresetId: z.string(),
  recommendedPresetName: z.string(),
  disclaimer: z.string(),
  generatedAt: z.string(),
  modelAvailable: z.boolean().optional(),
  preferLlm: z.boolean().optional(),
  beginnerModeRecommended: z.boolean().optional(),
  configChanges: z.array(objectRecordSchema).optional(),
  configItems: z.array(onboardingConfigItemSchema).optional(),
  todos: z.array(onboardingTodoItemSchema).optional(),
  todayPlan: z.array(onboardingPlanStepSchema).optional(),
  weekPlan: z.array(onboardingWeekStepSchema).optional(),
}).passthrough();

const onboardingApplySchema = z.object({
  success: z.boolean(),
  configVersion: z.string(),
  plan: onboardingPlanSchema,
  profile: objectRecordSchema,
  message: z.string(),
  appliedKeys: stringListSchema.optional(),
  appliedCount: finiteNumber.optional(),
  update: objectRecordSchema.optional(),
}).passthrough();

const onboardingStateSchema = z.object({
  exists: z.boolean(),
  status: z.string().nullable().optional(),
  profile: objectRecordSchema.nullable().optional(),
  plan: onboardingPlanSchema.nullable().optional(),
  appliedAt: z.string().nullable().optional(),
  appliedKeys: stringListSchema.optional(),
  configVersion: z.string().nullable().optional(),
}).passthrough();

const onboardingResetSchema = z.object({
  success: z.boolean(),
  reset: z.boolean(),
  message: z.string(),
}).passthrough();

function defaultPlanCollections(plan: OnboardingPlan): OnboardingPlan {
  if (!Array.isArray(plan.configChanges)) plan.configChanges = [];
  if (!Array.isArray(plan.configItems)) plan.configItems = [];
  if (!Array.isArray(plan.todos)) plan.todos = [];
  if (!Array.isArray(plan.todayPlan)) plan.todayPlan = [];
  if (!Array.isArray(plan.weekPlan)) plan.weekPlan = [];
  const featurePath = plan.featurePath as OnboardingFeaturePath | undefined;
  if (featurePath) {
    if (!Array.isArray(featurePath.primaryPath)) featurePath.primaryPath = [];
    if (!Array.isArray(featurePath.emphasize)) featurePath.emphasize = [];
    if (!Array.isArray(featurePath.defer)) featurePath.defer = [];
  }
  return plan;
}

function parseOnboardingPlan(data: unknown): OnboardingPlan {
  const parsed = parseCamelCasePayload<OnboardingPlan>(
    data,
    onboardingPlanSchema,
    'OnboardingPlanResponse',
    'onboarding',
  );
  return defaultPlanCollections(parsed);
}

function parseOnboardingApply(data: unknown): OnboardingApplyResult {
  const parsed = parseCamelCasePayload<OnboardingApplyResult>(
    data,
    onboardingApplySchema,
    'OnboardingApplyResponse',
    'onboarding',
  );
  if (!Array.isArray(parsed.appliedKeys)) parsed.appliedKeys = [];
  defaultPlanCollections(parsed.plan);
  return parsed;
}

function parseOnboardingState(data: unknown): OnboardingState {
  const parsed = parseCamelCasePayload<OnboardingState>(
    data,
    onboardingStateSchema,
    'OnboardingStateResponse',
    'onboarding',
  );
  if (!Array.isArray(parsed.appliedKeys)) parsed.appliedKeys = [];
  if (parsed.plan) defaultPlanCollections(parsed.plan);
  return parsed;
}

function toSnakeProfile(profile: UserOnboardingProfile): Record<string, unknown> {
  return {
    schema_version: profile.schemaVersion,
    experience_stage: profile.experienceStage,
    markets: profile.markets,
    goals: profile.goals,
    holdings: profile.holdings,
    interaction: profile.interaction,
    risk_tone: profile.riskTone,
    infrastructure: profile.infrastructure,
    report_language: profile.reportLanguage,
  };
}

export const onboardingApi = {
  async generatePlan(input: {
    profile: UserOnboardingProfile;
    modelAvailable?: boolean;
    preferLlm?: boolean;
  }): Promise<OnboardingPlan> {
    try {
      const response = await apiClient.post(`${BASE_PATH}/plan`, {
        profile: toSnakeProfile(input.profile),
        model_available: Boolean(input.modelAvailable),
        prefer_llm: Boolean(input.preferLlm),
      });
      return parseOnboardingPlan(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async applyPlan(input: {
    profile: UserOnboardingProfile;
    configVersion: string;
    confirm?: boolean;
    modelAvailable?: boolean;
    preferLlm?: boolean;
  }): Promise<OnboardingApplyResult> {
    try {
      const response = await apiClient.post(`${BASE_PATH}/apply`, {
        profile: toSnakeProfile(input.profile),
        config_version: input.configVersion,
        confirm: input.confirm !== false,
        model_available: Boolean(input.modelAvailable),
        prefer_llm: Boolean(input.preferLlm),
      });
      return parseOnboardingApply(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getState(): Promise<OnboardingState> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/state`);
      return parseOnboardingState(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async resetState(): Promise<{ success: boolean; reset: boolean; message: string }> {
    try {
      const response = await apiClient.delete(`${BASE_PATH}/state`);
      return parseCamelCasePayload<{ success: boolean; reset: boolean; message: string }>(
        response.data,
        onboardingResetSchema,
        'OnboardingResetResponse',
        'onboarding',
      );
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getFirstRunReadiness(): Promise<FirstRunReadiness> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/first-run`);
      return parseCamelCasePayload<FirstRunReadiness>(
        response.data,
        firstRunReadinessSchema,
        'onboarding.first-run',
        'onboarding',
      );
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getDemoAnalysis(reportLanguage: 'zh' | 'en' | 'ko' = 'zh'): Promise<DemoAnalysisPayload> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/demo-analysis`, {
        params: { report_language: reportLanguage },
      });
      return parseCamelCasePayload<DemoAnalysisPayload>(
        response.data,
        demoAnalysisSchema,
        'onboarding.demo-analysis',
        'onboarding',
      );
    } catch (error) {
      throw getParsedApiError(error);
    }
  },
};
