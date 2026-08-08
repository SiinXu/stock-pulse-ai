// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

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
  reportLanguage: string;
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
export type FirstRunPrimaryCta = 'continue' | 'start_with_local' | 'view_demo';

export interface LocalRuntimeSnapshot {
  available: boolean;
  backend?: string | null;
  baseUrl?: string | null;
  models: string[];
  suggestedProfile: Record<string, string>;
  reason: string;
  detectEnabled: boolean;
}

export interface FirstRunReadiness {
  schemaVersion: number;
  isFreshEnvironment: boolean;
  hasPrimaryModel: boolean;
  beginnerModeRecommended: boolean;
  primaryPath: FirstRunPrimaryPath | string;
  primaryCta: FirstRunPrimaryCta | string;
  headline: string;
  localRuntime: LocalRuntimeSnapshot;
  recommendedPresetId?: string | null;
  recommendedPresetName?: string | null;
  suggestedProfile: Record<string, string>;
  demoAvailable: boolean;
  configMutated: boolean;
  existingConfigUntouched: boolean;
  generatedAt: string;
}

export interface DemoAnalysisPayload {
  schemaVersion: number;
  isSample: boolean;
  sampleBanner: string;
  sampleDisclaimer: string;
  queryId: string;
  stockCode: string;
  stockName: string;
  createdAt: string;
  report: {
    meta: {
      queryId?: string;
      stockCode: string;
      stockName: string;
      reportType: string;
      reportLanguage?: string;
      createdAt: string;
      currentPrice?: number | null;
      changePct?: number | null;
      modelUsed?: string | null;
    };
    summary: {
      analysisSummary: string;
      operationAdvice: string;
      action?: string | null;
      actionLabel?: string | null;
      trendPrediction: string;
      sentimentScore: number;
      sentimentLabel?: string;
    };
    strategy?: Record<string, unknown>;
    details?: Record<string, unknown>;
  };
}

