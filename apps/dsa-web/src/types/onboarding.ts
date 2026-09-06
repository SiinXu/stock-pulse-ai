// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { components, operations, paths } from './api.generated';
import type { ReportLanguage } from './analysis';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiProfile = components['schemas']['UserOnboardingProfile'];
type OpenApiFeaturePath = components['schemas']['OnboardingFeaturePath'];
type OpenApiConfigItem = components['schemas']['OnboardingConfigItem'];
type OpenApiPlanStep = components['schemas']['OnboardingPlanStep'];
type OpenApiTodo = components['schemas']['OnboardingTodoItem'];
type OpenApiWeekStep = components['schemas']['OnboardingWeekStep'];
type OpenApiPlan = components['schemas']['OnboardingPlanResponse'];
type OpenApiApply = components['schemas']['OnboardingApplyResponse'];
type OpenApiState = components['schemas']['OnboardingStateResponse'];
type OpenApiRuntime = components['schemas']['LocalRuntimeSnapshot'];
type OpenApiFirstRun = components['schemas']['FirstRunReadinessResponse'];
type OpenApiDemo = components['schemas']['DemoAnalysisResponse'];
type OpenApiReset = components['schemas']['OnboardingResetResponse'];

type OpenApiStateOp = operations['get_onboarding_state_api_v1_onboarding_state_get'];
type OpenApiPlanOp = operations['generate_onboarding_plan_api_v1_onboarding_plan_post'];
type OpenApiApplyOp = operations['apply_onboarding_plan_api_v1_onboarding_apply_post'];
type OpenApiFirstRunOp = operations['get_first_run_readiness_api_v1_onboarding_first_run_get'];
type OpenApiDemoOp = operations['get_demo_analysis_api_v1_onboarding_demo_analysis_get'];
type OpenApiResetOp = operations['reset_onboarding_state_api_v1_onboarding_state_delete'];

type OpenApiStatePathGet = paths['/api/v1/onboarding/state']['get'];
type OpenApiPlanPathPost = paths['/api/v1/onboarding/plan']['post'];
type OpenApiApplyPathPost = paths['/api/v1/onboarding/apply']['post'];
type OpenApiFirstRunPathGet = paths['/api/v1/onboarding/first-run']['get'];
type OpenApiDemoPathGet = paths['/api/v1/onboarding/demo-analysis']['get'];
type OpenApiResetPathDelete = paths['/api/v1/onboarding/state']['delete'];

type OpenApiStateGet200 = OpenApiStateOp['responses']['200']['content']['application/json'];
type OpenApiPlanPost200 = OpenApiPlanOp['responses']['200']['content']['application/json'];
type OpenApiApplyPost200 = OpenApiApplyOp['responses']['200']['content']['application/json'];
type OpenApiFirstRunGet200 = OpenApiFirstRunOp['responses']['200']['content']['application/json'];
type OpenApiDemoGet200 = OpenApiDemoOp['responses']['200']['content']['application/json'];
type OpenApiResetDelete200 = OpenApiResetOp['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _State200IsState = _Assert<OpenApiStateGet200 extends OpenApiState ? true : false>;
type _StateIsState200 = _Assert<OpenApiState extends OpenApiStateGet200 ? true : false>;
type _StateOpIsPath = _Assert<OpenApiStateOp extends OpenApiStatePathGet ? true : false>;
type _PathIsStateOp = _Assert<OpenApiStatePathGet extends OpenApiStateOp ? true : false>;
type _StateGetNeverRequestBody = _Assert<OpenApiStateOp extends { requestBody?: never } ? true : false>;
type _StateHas200 = _Assert<200 extends keyof OpenApiStateOp['responses'] ? true : false>;
type _StateLacks201 = _Assert<201 extends keyof OpenApiStateOp['responses'] ? false : true>;
type _Plan200IsPlan = _Assert<OpenApiPlanPost200 extends OpenApiPlan ? true : false>;
type _PlanIsPlan200 = _Assert<OpenApiPlan extends OpenApiPlanPost200 ? true : false>;
type _PlanOpIsPath = _Assert<OpenApiPlanOp extends OpenApiPlanPathPost ? true : false>;
type _PathIsPlanOp = _Assert<OpenApiPlanPathPost extends OpenApiPlanOp ? true : false>;
type _PlanHas200 = _Assert<200 extends keyof OpenApiPlanOp['responses'] ? true : false>;
type _PlanLacks201 = _Assert<201 extends keyof OpenApiPlanOp['responses'] ? false : true>;
type _Apply200IsApply = _Assert<OpenApiApplyPost200 extends OpenApiApply ? true : false>;
type _ApplyIsApply200 = _Assert<OpenApiApply extends OpenApiApplyPost200 ? true : false>;
type _ApplyOpIsPath = _Assert<OpenApiApplyOp extends OpenApiApplyPathPost ? true : false>;
type _PathIsApplyOp = _Assert<OpenApiApplyPathPost extends OpenApiApplyOp ? true : false>;
type _ApplyHas200 = _Assert<200 extends keyof OpenApiApplyOp['responses'] ? true : false>;
type _ApplyLacks201 = _Assert<201 extends keyof OpenApiApplyOp['responses'] ? false : true>;
type _FirstRun200IsFirstRun = _Assert<OpenApiFirstRunGet200 extends OpenApiFirstRun ? true : false>;
type _FirstRunIsFirstRun200 = _Assert<OpenApiFirstRun extends OpenApiFirstRunGet200 ? true : false>;
type _FirstRunOpIsPath = _Assert<OpenApiFirstRunOp extends OpenApiFirstRunPathGet ? true : false>;
type _PathIsFirstRunOp = _Assert<OpenApiFirstRunPathGet extends OpenApiFirstRunOp ? true : false>;
type _FirstRunGetNeverRequestBody = _Assert<OpenApiFirstRunOp extends { requestBody?: never } ? true : false>;
type _FirstRunHas200 = _Assert<200 extends keyof OpenApiFirstRunOp['responses'] ? true : false>;
type _FirstRunLacks201 = _Assert<201 extends keyof OpenApiFirstRunOp['responses'] ? false : true>;
type _Demo200IsDemo = _Assert<OpenApiDemoGet200 extends OpenApiDemo ? true : false>;
type _DemoIsDemo200 = _Assert<OpenApiDemo extends OpenApiDemoGet200 ? true : false>;
type _DemoOpIsPath = _Assert<OpenApiDemoOp extends OpenApiDemoPathGet ? true : false>;
type _PathIsDemoOp = _Assert<OpenApiDemoPathGet extends OpenApiDemoOp ? true : false>;
type _DemoGetNeverRequestBody = _Assert<OpenApiDemoOp extends { requestBody?: never } ? true : false>;
type _DemoHas200 = _Assert<200 extends keyof OpenApiDemoOp['responses'] ? true : false>;
type _DemoLacks201 = _Assert<201 extends keyof OpenApiDemoOp['responses'] ? false : true>;
type _Reset200IsReset = _Assert<OpenApiResetDelete200 extends OpenApiReset ? true : false>;
type _ResetIsReset200 = _Assert<OpenApiReset extends OpenApiResetDelete200 ? true : false>;
type _ResetOpIsPath = _Assert<OpenApiResetOp extends OpenApiResetPathDelete ? true : false>;
type _PathIsResetOp = _Assert<OpenApiResetPathDelete extends OpenApiResetOp ? true : false>;
type _ResetGetNeverRequestBody = _Assert<OpenApiResetOp extends { requestBody?: never } ? true : false>;
type _ResetHas200 = _Assert<200 extends keyof OpenApiResetOp['responses'] ? true : false>;
type _ResetLacks201 = _Assert<201 extends keyof OpenApiResetOp['responses'] ? false : true>;

type _OpenApiAnchors = [
  _State200IsState,
  _StateIsState200,
  _StateOpIsPath,
  _PathIsStateOp,
  _StateGetNeverRequestBody,
  _StateHas200,
  _StateLacks201,
  _Plan200IsPlan,
  _PlanIsPlan200,
  _PlanOpIsPath,
  _PathIsPlanOp,
  _PlanHas200,
  _PlanLacks201,
  _Apply200IsApply,
  _ApplyIsApply200,
  _ApplyOpIsPath,
  _PathIsApplyOp,
  _ApplyHas200,
  _ApplyLacks201,
  _FirstRun200IsFirstRun,
  _FirstRunIsFirstRun200,
  _FirstRunOpIsPath,
  _PathIsFirstRunOp,
  _FirstRunGetNeverRequestBody,
  _FirstRunHas200,
  _FirstRunLacks201,
  _Demo200IsDemo,
  _DemoIsDemo200,
  _DemoOpIsPath,
  _PathIsDemoOp,
  _DemoGetNeverRequestBody,
  _DemoHas200,
  _DemoLacks201,
  _Reset200IsReset,
  _ResetIsReset200,
  _ResetOpIsPath,
  _PathIsResetOp,
  _ResetGetNeverRequestBody,
  _ResetHas200,
  _ResetLacks201,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

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

export type UserOnboardingProfile = Override<CamelizeKeys<OpenApiProfile>, {
  experienceStage: OnboardingExperienceStage;
  markets: OnboardingMarket[];
  goals: OnboardingGoal[];
  holdings: OnboardingHoldings;
  interaction: OnboardingInteraction;
  riskTone: OnboardingRiskTone;
  infrastructure: OnboardingInfrastructure;
  reportLanguage: ReportLanguage;
}>;

export type OnboardingConfigItem = CamelizeKeys<OpenApiConfigItem>;
export type OnboardingTodoItem = CamelizeKeys<OpenApiTodo>;
export type OnboardingPlanStep = _BindOpenApiAnchors<CamelizeKeys<OpenApiPlanStep>>;
export type OnboardingWeekStep = CamelizeKeys<OpenApiWeekStep>;

export type OnboardingFeaturePath = Override<CamelizeKeys<OpenApiFeaturePath>, {
  primaryPath: string[];
  emphasize: string[];
  defer: string[];
}>;

export type OnboardingPlan = Override<CamelizeKeys<OpenApiPlan>, {
  profile: UserOnboardingProfile | Record<string, unknown>;
  featurePath: OnboardingFeaturePath;
  configChanges: Array<Record<string, string>>;
  configItems: OnboardingConfigItem[];
  todos: OnboardingTodoItem[];
  todayPlan: OnboardingPlanStep[];
  weekPlan: OnboardingWeekStep[];
}>;

export type OnboardingApplyResult = Override<CamelizeKeys<OpenApiApply>, {
  appliedKeys: string[];
  plan: OnboardingPlan;
  profile: UserOnboardingProfile | Record<string, unknown>;
}>;

export type OnboardingState = Override<CamelizeKeys<OpenApiState>, {
  appliedKeys: string[];
  profile?: UserOnboardingProfile | Record<string, unknown> | null;
  plan?: OnboardingPlan | null;
}>;

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

export type LocalRuntimeSnapshot = Override<CamelizeKeys<OpenApiRuntime>, {
  models: string[];
  suggestedProfile: Record<string, string>;
}>;

export type FirstRunReadiness = Override<CamelizeKeys<OpenApiFirstRun>, {
  reasonParams: Record<string, string>;
  localRuntime: LocalRuntimeSnapshot;
  suggestedProfile: Record<string, string>;
}>;

export type DemoAnalysisPayload = Override<CamelizeKeys<OpenApiDemo>, {
  report: Override<CamelizeKeys<OpenApiDemo>['report'], {
    details: { news: string[]; technical: string[] };
    strategy: {
      idealBuy: null;
      secondaryBuy: null;
      stopLoss: null;
      takeProfit: null;
    };
  }>;
}>;

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
