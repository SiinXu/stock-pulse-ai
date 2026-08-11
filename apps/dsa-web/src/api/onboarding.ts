// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { getParsedApiError } from './error';
import { toCamelCase } from './utils';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type {
  DemoAnalysisPayload,
  FirstRunReadiness,
  OnboardingApplyResult,
  OnboardingPlan,
  OnboardingState,
  UserOnboardingProfile,
} from '../types/onboarding';

const BASE_PATH = '/api/v1/onboarding';

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
      return toCamelCase<OnboardingPlan>(response.data);
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
      return toCamelCase<OnboardingApplyResult>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getState(): Promise<OnboardingState> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/state`);
      return toCamelCase<OnboardingState>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async resetState(): Promise<{ success: boolean; reset: boolean; message: string }> {
    try {
      const response = await apiClient.delete(`${BASE_PATH}/state`);
      return toCamelCase(response.data);
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
