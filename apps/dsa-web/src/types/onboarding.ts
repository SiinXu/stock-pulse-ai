// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReportLanguage } from './analysis';

export type OnboardingExperienceStage = 'beginner' | 'report_reader' | 'has_system';
export type OnboardingMarket = 'cn' | 'hk' | 'us';
export type OnboardingGoal =
  | 'daily_push'
  | 'pre_post_market'
  | 'holdings_risk'
  | 'strategy_validation';
export type OnboardingHoldings = 'none' | 'watchlist' | 'bookkeeping';
export type OnboardingInteraction = 'push' | 'web' | 'chat';
export type OnboardingRiskTone = 'conservative' | 'balanced' | 'assertive';
export type OnboardingInfrastructure = 'cloud_key' | 'local_models' | 'free_only';

export interface UserOnboardingProfile {
  schemaVersion: number;
  experienceStage: OnboardingExperienceStage;
  markets: OnboardingMarket[];
  goals: OnboardingGoal[];
  holdings: OnboardingHoldings;
  interaction: OnboardingInteraction;
  riskTone: OnboardingRiskTone;
  infrastructure: OnboardingInfrastructure;
  reportLanguage: ReportLanguage;
}

export interface OnboardingConfigItem {
  key: string;
  value: string;
}

export interface OnboardingTodoItem {
  id: string;
  priority: number;
  title: string;
  description: string;
  href?: string | null;
  kind: string;
}

export interface OnboardingPlanStep {
  id: string;
  title: string;
  detail: string;
}

export interface OnboardingWeekStep {
  day: string;
  title: string;
  detail: string;
}

export interface OnboardingFeaturePath {
  stage: string;
  label: string;
  primaryPath: string[];
  emphasize: string[];
  defer: string[];
}

export interface OnboardingPlan {
  schemaVersion: number;
  engine: string;
  llmNote: string;
  modelAvailable: boolean;
  preferLlm: boolean;
  profile: UserOnboardingProfile | Record<string, unknown>;
  featureStage: string;
  featurePath: OnboardingFeaturePath;
  recommendedPresetId: string;
  recommendedPresetName: string;
  beginnerModeRecommended: boolean;
  configChanges: Array<Record<string, string>>;
  configItems: OnboardingConfigItem[];
  todos: OnboardingTodoItem[];
  todayPlan: OnboardingPlanStep[];
  weekPlan: OnboardingWeekStep[];
  disclaimer: string;
  generatedAt: string;
}

export interface OnboardingApplyResult {
  success: boolean;
  configVersion: string;
  appliedKeys: string[];
  appliedCount: number;
  plan: OnboardingPlan;
  profile: UserOnboardingProfile | Record<string, unknown>;
  message: string;
  update?: Record<string, unknown>;
}

export interface OnboardingState {
  exists: boolean;
  status?: string | null;
  profile?: UserOnboardingProfile | Record<string, unknown> | null;
  plan?: OnboardingPlan | null;
  appliedAt?: string | null;
  appliedKeys: string[];
  configVersion?: string | null;
}

export const DEFAULT_ONBOARDING_PROFILE: UserOnboardingProfile = {
  schemaVersion: 1,
  experienceStage: 'beginner',
  markets: ['cn'],
  goals: ['pre_post_market'],
  holdings: 'none',
  interaction: 'web',
  riskTone: 'balanced',
  infrastructure: 'cloud_key',
  reportLanguage: 'zh',
};

export const ONBOARDING_DRAFT_STORAGE_KEY = 'dsa-onboarding-draft-v1';
export const ONBOARDING_PLAN_STORAGE_KEY = 'dsa-onboarding-plan-v1';

/** Server first-run readiness path (zero-config #796). */
export type FirstRunPrimaryPath = 'configured' | 'local_ollama' | 'demo';
export type FirstRunPrimaryCta = 'continue' | 'open_local_setup' | 'view_demo';
export type FirstRunReasonCode =
  | 'primary_model_configured'
  | 'local_model_ready'
  | 'local_runtime_no_models'
  | 'local_detect_disabled'
  | 'local_runtime_unavailable';
export type LocalRuntimeReasonCode =
  | 'ollama_ready'
  | 'ollama_no_models'
  | 'detect_disabled'
  | 'ollama_unreachable';

export interface LocalRuntimeSnapshot {
  reachable: boolean;
  modelsAvailable: boolean;
  runnable: boolean;
  backend?: 'ollama' | null;
  baseUrl?: string | null;
  models: string[];
  suggestedProfile: Record<string, string>;
  reasonCode: LocalRuntimeReasonCode;
  detectEnabled: boolean;
}

export interface FirstRunReadiness {
  schemaVersion: 1;
  isFreshEnvironment: boolean;
  hasPrimaryModel: boolean;
  beginnerModeRecommended: boolean;
  primaryPath: FirstRunPrimaryPath;
  primaryCta: FirstRunPrimaryCta;
  reasonCode: FirstRunReasonCode;
  reasonParams: Record<string, string>;
  localRuntime: LocalRuntimeSnapshot;
  recommendedPresetId?: 'local-first' | null;
  suggestedProfile: Record<string, string>;
  demoAvailable: true;
  configMutated: false;
  existingConfigUntouched: true;
  snapshotId: string;
  generatedAt: string;
}

export interface DemoAnalysisPayload {
  schemaVersion: 1;
  isSample: true;
  sampleBanner: string;
  sampleDisclaimer: string;
  queryId: 'demo-sample-analysis-v1';
  stockCode: '600519';
  stockName: string;
  createdAt: string;
  report: {
    meta: {
      queryId: 'demo-sample-analysis-v1';
      stockCode: '600519';
      stockName: string;
      reportType: 'brief';
      reportLanguage: 'zh' | 'en' | 'ko';
      createdAt: string;
      currentPrice: null;
      changePct: null;
      modelUsed: 'demo-fixture/offline';
    };
    summary: {
      analysisSummary: string;
      operationAdvice: string;
      action: 'watch';
      actionLabel: string;
      trendPrediction: string;
      sentimentScore: number;
      sentimentLabel: '中性' | 'Neutral' | '중립';
    };
    strategy: {
      idealBuy: null;
      secondaryBuy: null;
      stopLoss: null;
      takeProfit: null;
    };
    details: {
      news: string[];
      technical: string[];
    };
  };
}
