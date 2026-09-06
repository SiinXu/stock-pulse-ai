// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Onboarding from '../onboarding';
import {
  DEFAULT_ONBOARDING_PROFILE,
  ONBOARDING_DRAFT_STORAGE_KEY,
  ONBOARDING_PLAN_STORAGE_KEY,
} from '../onboarding';
import type {
  DemoAnalysisPayload,
  FirstRunReadiness,
  LocalRuntimeSnapshot,
  OnboardingApplyResult,
  OnboardingConfigItem,
  OnboardingExperienceStage,
  OnboardingFeaturePath,
  OnboardingGoal,
  OnboardingHoldings,
  OnboardingInfrastructure,
  OnboardingInteraction,
  OnboardingMarket,
  OnboardingPlan,
  OnboardingPlanStep,
  OnboardingRiskTone,
  OnboardingState,
  OnboardingTodoItem,
  OnboardingWeekStep,
  UserOnboardingProfile,
} from '../onboarding';
import type { ReportLanguage } from '../analysis';

type OpenApiProfile = components['schemas']['UserOnboardingProfile'];
type OpenApiFeaturePath = components['schemas']['OnboardingFeaturePath'];
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

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _TwelveComponents = _Assert<
  (
    | 'UserOnboardingProfile'
    | 'OnboardingFeaturePath'
    | 'OnboardingConfigItem'
    | 'OnboardingPlanStep'
    | 'OnboardingTodoItem'
    | 'OnboardingWeekStep'
    | 'OnboardingPlanResponse'
    | 'OnboardingApplyResponse'
    | 'OnboardingStateResponse'
    | 'LocalRuntimeSnapshot'
    | 'FirstRunReadinessResponse'
    | 'DemoAnalysisResponse'
  ) extends keyof components['schemas'] ? true : false
>;

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

type _PublicPlanNotPath200 = _Assert<OnboardingPlan extends OpenApiPlanPost200 ? false : true>;
type _Path200NotPublicPlan = _Assert<OpenApiPlanPost200 extends OnboardingPlan ? false : true>;
type _PublicApplyNotPath200 = _Assert<OnboardingApplyResult extends OpenApiApplyPost200 ? false : true>;
type _Path200NotPublicApply = _Assert<OpenApiApplyPost200 extends OnboardingApplyResult ? false : true>;
type _PublicStateNotPath200 = _Assert<OnboardingState extends OpenApiStateGet200 ? false : true>;
type _Path200NotPublicState = _Assert<OpenApiStateGet200 extends OnboardingState ? false : true>;
type _PublicFirstRunNotPath200 = _Assert<FirstRunReadiness extends OpenApiFirstRunGet200 ? false : true>;
type _Path200NotPublicFirstRun = _Assert<OpenApiFirstRunGet200 extends FirstRunReadiness ? false : true>;
type _PublicDemoNotPath200 = _Assert<DemoAnalysisPayload extends OpenApiDemoGet200 ? false : true>;
type _Path200NotPublicDemo = _Assert<OpenApiDemoGet200 extends DemoAnalysisPayload ? false : true>;

type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof OnboardingPlan ? true : false>;
type _UiHasLlmNote = _Assert<'llmNote' extends keyof OnboardingPlan ? true : false>;
type _UiHasFeaturePath = _Assert<'featurePath' extends keyof OnboardingPlan ? true : false>;
type _UiHasAppliedKeys = _Assert<'appliedKeys' extends keyof OnboardingApplyResult ? true : false>;
type _UiHasReasonParams = _Assert<'reasonParams' extends keyof FirstRunReadiness ? true : false>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof OnboardingPlan ? false : true>;
type _UiLacksLlmNoteSnake = _Assert<'llm_note' extends keyof OnboardingPlan ? false : true>;
type _UiLacksFeaturePathSnake = _Assert<'feature_path' extends keyof OnboardingPlan ? false : true>;
type _UiLacksAppliedKeysSnake = _Assert<'applied_keys' extends keyof OnboardingApplyResult ? false : true>;
type _UiLacksReasonParamsSnake = _Assert<'reason_params' extends keyof FirstRunReadiness ? false : true>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiPlan ? true : false>;
type _GeneratedHasLlmNoteSnake = _Assert<'llm_note' extends keyof OpenApiPlan ? true : false>;
type _GeneratedHasFeaturePathSnake = _Assert<'feature_path' extends keyof OpenApiPlan ? true : false>;
type _GeneratedHasAppliedKeysSnake = _Assert<'applied_keys' extends keyof OpenApiApply ? true : false>;
type _GeneratedHasReasonParamsSnake = _Assert<'reason_params' extends keyof OpenApiFirstRun ? true : false>;
type _GeneratedLacksSchemaVersionCamel = _Assert<'schemaVersion' extends keyof OpenApiPlan ? false : true>;
type _GeneratedLacksLlmNoteCamel = _Assert<'llmNote' extends keyof OpenApiPlan ? false : true>;
type _GeneratedLacksFeaturePathCamel = _Assert<'featurePath' extends keyof OpenApiPlan ? false : true>;
type _GeneratedLacksAppliedKeysCamel = _Assert<'appliedKeys' extends keyof OpenApiApply ? false : true>;
type _GeneratedLacksReasonParamsCamel = _Assert<'reasonParams' extends keyof OpenApiFirstRun ? false : true>;

type _UiTodosRequired = _Assert<IsOptional<OnboardingPlan, 'todos'> extends false ? true : false>;
type _UiConfigChangesRequired = _Assert<IsOptional<OnboardingPlan, 'configChanges'> extends false ? true : false>;
type _GeneratedTodosOptional = _Assert<IsOptional<OpenApiPlan, 'todos'>>;
type _NaiveTodosOptional = _Assert<IsOptional<CamelizeKeys<OpenApiPlan>, 'todos'>>;
type _NaiveConfigChangesOptional = _Assert<IsOptional<CamelizeKeys<OpenApiPlan>, 'configChanges'>>;
type _UiPrimaryPathRequired = _Assert<IsOptional<OnboardingFeaturePath, 'primaryPath'> extends false ? true : false>;
type _NaivePrimaryPathOptional = _Assert<IsOptional<CamelizeKeys<OpenApiFeaturePath>, 'primaryPath'>>;
type _UiReasonParamsRequired = _Assert<IsOptional<FirstRunReadiness, 'reasonParams'> extends false ? true : false>;
type _UiSuggestedProfileRequired = _Assert<
  IsOptional<FirstRunReadiness, 'suggestedProfile'> extends false ? true : false
>;
type _NaiveReasonParamsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiFirstRun>, 'reasonParams'>>;
type _UiModelsRequired = _Assert<IsOptional<LocalRuntimeSnapshot, 'models'> extends false ? true : false>;
type _NaiveModelsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiRuntime>, 'models'>>;
type _UiApplyAppliedKeysRequired = _Assert<
  IsOptional<OnboardingApplyResult, 'appliedKeys'> extends false ? true : false
>;
type _UiStateAppliedKeysRequired = _Assert<IsOptional<OnboardingState, 'appliedKeys'> extends false ? true : false>;
type _NaiveApplyAppliedKeysOptional = _Assert<IsOptional<CamelizeKeys<OpenApiApply>, 'appliedKeys'>>;
type _NaiveStateAppliedKeysOptional = _Assert<IsOptional<CamelizeKeys<OpenApiState>, 'appliedKeys'>>;
type NaivePlanProfile = CamelizeKeys<OpenApiPlan>['profile'];

interface ClosedOnboardingProfile {
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

type _ClosedProfileNotNaiveBag = _Assert<ClosedOnboardingProfile extends NaivePlanProfile ? false : true>;
type _UiProfileAssignsToPlanProfile = _Assert<
  UserOnboardingProfile extends OnboardingPlan['profile'] ? true : false
>;

type _CompileTimePins = [
  _TwelveComponents,
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
  _PublicPlanNotPath200,
  _Path200NotPublicPlan,
  _PublicApplyNotPath200,
  _Path200NotPublicApply,
  _PublicStateNotPath200,
  _Path200NotPublicState,
  _PublicFirstRunNotPath200,
  _Path200NotPublicFirstRun,
  _PublicDemoNotPath200,
  _Path200NotPublicDemo,
  _UiHasSchemaVersion,
  _UiHasLlmNote,
  _UiHasFeaturePath,
  _UiHasAppliedKeys,
  _UiHasReasonParams,
  _UiLacksSchemaVersionSnake,
  _UiLacksLlmNoteSnake,
  _UiLacksFeaturePathSnake,
  _UiLacksAppliedKeysSnake,
  _UiLacksReasonParamsSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasLlmNoteSnake,
  _GeneratedHasFeaturePathSnake,
  _GeneratedHasAppliedKeysSnake,
  _GeneratedHasReasonParamsSnake,
  _GeneratedLacksSchemaVersionCamel,
  _GeneratedLacksLlmNoteCamel,
  _GeneratedLacksFeaturePathCamel,
  _GeneratedLacksAppliedKeysCamel,
  _GeneratedLacksReasonParamsCamel,
  _UiTodosRequired,
  _UiConfigChangesRequired,
  _GeneratedTodosOptional,
  _NaiveTodosOptional,
  _NaiveConfigChangesOptional,
  _UiPrimaryPathRequired,
  _NaivePrimaryPathOptional,
  _UiReasonParamsRequired,
  _UiSuggestedProfileRequired,
  _NaiveReasonParamsOptional,
  _UiModelsRequired,
  _NaiveModelsOptional,
  _UiApplyAppliedKeysRequired,
  _UiStateAppliedKeysRequired,
  _NaiveApplyAppliedKeysOptional,
  _NaiveStateAppliedKeysOptional,
  _ClosedProfileNotNaiveBag,
  _UiProfileAssignsToPlanProfile,
];

const featurePath = {
  stage: 'L0',
  label: 'Cold start',
  primaryPath: ['Configure model'],
  emphasize: ['home'],
  defer: ['committee'],
};

const planBase = {
  schemaVersion: 1,
  engine: 'rules',
  llmNote: 'note',
  modelAvailable: false,
  preferLlm: false,
  profile: DEFAULT_ONBOARDING_PROFILE,
  featureStage: 'L0',
  featurePath,
  recommendedPresetId: 'p',
  recommendedPresetName: 'n',
  beginnerModeRecommended: true,
  configChanges: [] as Array<Record<string, string>>,
  configItems: [] as OnboardingConfigItem[],
  todos: [] as OnboardingTodoItem[],
  todayPlan: [] as OnboardingPlanStep[],
  weekPlan: [] as OnboardingWeekStep[],
  disclaimer: 'd',
  generatedAt: '2026-08-06T00:00:00Z',
};

const firstRunBase = {
  schemaVersion: 1 as const,
  isFreshEnvironment: true,
  hasPrimaryModel: false,
  beginnerModeRecommended: true,
  primaryPath: 'demo' as const,
  primaryCta: 'view_demo' as const,
  reasonCode: 'local_runtime_unavailable' as const,
  reasonParams: {} as Record<string, string>,
  localRuntime: {
    reachable: false,
    modelsAvailable: false,
    runnable: false,
    models: [] as string[],
    suggestedProfile: {} as Record<string, string>,
    reasonCode: 'ollama_unreachable' as const,
    detectEnabled: true,
  },
  suggestedProfile: {} as Record<string, string>,
  demoAvailable: true as const,
  configMutated: false as const,
  existingConfigUntouched: true as const,
  snapshotId: '0123456789abcdef01234567',
  generatedAt: '2026-08-09T00:00:00Z',
};

const bagProfile: Record<string, unknown> = { schemaVersion: 1 };

const uiPlan: OnboardingPlan = planBase;
void uiPlan;

// @ts-expect-error extraTag is not a public featurePath field
const extraFeature: OnboardingFeaturePath = { ...featurePath, extraTag: 'x' };

// @ts-expect-error futurePlanFlag is not a public plan field
const extraPlan: OnboardingPlan = { ...planBase, futurePlanFlag: true };

// @ts-expect-error futureFirstRunFlag is not a public first-run field
const extraFirstRun: FirstRunReadiness = { ...firstRunBase, futureFirstRunFlag: true };

// @ts-expect-error public plan uses schemaVersion, not schema_version
const snakePlan: OnboardingPlan = { ...planBase, schema_version: 1 };

const planMissingCollections = {
  schemaVersion: 1,
  engine: 'rules',
  llmNote: 'note',
  modelAvailable: false,
  preferLlm: false,
  profile: bagProfile,
  featureStage: 'L0',
  featurePath,
  recommendedPresetId: 'p',
  recommendedPresetName: 'n',
  beginnerModeRecommended: true,
  disclaimer: 'd',
  generatedAt: '2026-08-06T00:00:00Z',
};
const naiveMissingCollections: CamelizeKeys<OpenApiPlan> = planMissingCollections;
void naiveMissingCollections;
// @ts-expect-error public plan collections stay required
const publicMissingCollections: OnboardingPlan = planMissingCollections;
void publicMissingCollections;

const shortFeature = { stage: 'L0', label: 'Cold start' };
const naiveShortFeature: CamelizeKeys<OpenApiFeaturePath> = shortFeature;
void naiveShortFeature;
// @ts-expect-error public featurePath arrays stay required
const publicShortFeature: OnboardingFeaturePath = shortFeature;
void publicShortFeature;

const { reasonParams: _rp, suggestedProfile: _sp, ...firstRunMissingBags } = firstRunBase;
void _rp;
void _sp;
const naiveMissingBags: CamelizeKeys<OpenApiFirstRun> = firstRunMissingBags;
void naiveMissingBags;
// @ts-expect-error public first-run reasonParams/suggestedProfile stay required
const publicMissingBags: FirstRunReadiness = firstRunMissingBags;
void publicMissingBags;

const runtimeMissingModels = {
  reachable: false,
  modelsAvailable: false,
  runnable: false,
  suggestedProfile: {},
  reasonCode: 'ollama_unreachable' as const,
  detectEnabled: true,
};
const naiveMissingModels: CamelizeKeys<OpenApiRuntime> = runtimeMissingModels;
void naiveMissingModels;
// @ts-expect-error public LocalRuntimeSnapshot.models stays required
const publicMissingModels: LocalRuntimeSnapshot = runtimeMissingModels;
void publicMissingModels;

const applyMissingKeys = {
  success: true,
  configVersion: 'v1',
  appliedCount: 0,
  plan: { ...planBase, profile: bagProfile },
  profile: bagProfile,
  message: 'ok',
};
const naiveApplyMissing: CamelizeKeys<OpenApiApply> = applyMissingKeys;
void naiveApplyMissing;
// @ts-expect-error public appliedKeys stays required
const publicApplyMissing: OnboardingApplyResult = applyMissingKeys;
void publicApplyMissing;

const naiveStateMissing: CamelizeKeys<OpenApiState> = { exists: true };
void naiveStateMissing;
// @ts-expect-error public appliedKeys stays required
const publicStateMissing: OnboardingState = { exists: true };
void publicStateMissing;

const uiProfile: UserOnboardingProfile = DEFAULT_ONBOARDING_PROFILE;
void uiProfile;
const naiveProfile: CamelizeKeys<OpenApiProfile> = DEFAULT_ONBOARDING_PROFILE;
void naiveProfile;
const uiPlanProfile: OnboardingPlan['profile'] = DEFAULT_ONBOARDING_PROFILE;
void uiPlanProfile;
const closedProfile: ClosedOnboardingProfile = DEFAULT_ONBOARDING_PROFILE;
void closedProfile;
// @ts-expect-error closed interface profile lacks the naive generated bag index signature
const naiveClosedProfile: NaivePlanProfile = closedProfile;
void naiveClosedProfile;

const badStage = { ...DEFAULT_ONBOARDING_PROFILE, experienceStage: 'not-a-stage' };
const naiveBadStage: CamelizeKeys<OpenApiProfile> = badStage;
void naiveBadStage;
// @ts-expect-error public experienceStage is a closed union
const publicBadStage: UserOnboardingProfile = badStage;
void publicBadStage;

void extraFeature;
void extraPlan;
void extraFirstRun;
void snakePlan;

describe('onboarding OpenAPI type bind', () => {
  it('keeps runtime constants exported with exact storage keys', () => {
    expect(DEFAULT_ONBOARDING_PROFILE.schemaVersion).toBe(1);
    expect(Onboarding.DEFAULT_ONBOARDING_PROFILE.schemaVersion).toBe(1);
    expect(ONBOARDING_DRAFT_STORAGE_KEY).toBe('dsa-onboarding-draft-v1');
    expect(ONBOARDING_PLAN_STORAGE_KEY).toBe('dsa-onboarding-plan-v1');
    expect(Onboarding.ONBOARDING_DRAFT_STORAGE_KEY).toBe('dsa-onboarding-draft-v1');
    expect(Onboarding.ONBOARDING_PLAN_STORAGE_KEY).toBe('dsa-onboarding-plan-v1');
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200 not 201', () => {
    expectTypeOf<OpenApiStateGet200>().toEqualTypeOf<OpenApiState>();
    expectTypeOf<OpenApiPlanPost200>().toEqualTypeOf<OpenApiPlan>();
    expectTypeOf<OpenApiApplyPost200>().toEqualTypeOf<OpenApiApply>();
    expectTypeOf<OpenApiFirstRunGet200>().toEqualTypeOf<OpenApiFirstRun>();
    expectTypeOf<OpenApiDemoGet200>().toEqualTypeOf<OpenApiDemo>();
    expectTypeOf<OpenApiResetDelete200>().toEqualTypeOf<OpenApiReset>();
    expectTypeOf<OpenApiStateOp>().toEqualTypeOf<OpenApiStatePathGet>();
    expectTypeOf<OpenApiPlanOp>().toEqualTypeOf<OpenApiPlanPathPost>();
    expectTypeOf<OpenApiApplyOp>().toEqualTypeOf<OpenApiApplyPathPost>();
    expectTypeOf<OpenApiFirstRunOp>().toEqualTypeOf<OpenApiFirstRunPathGet>();
    expectTypeOf<OpenApiDemoOp>().toEqualTypeOf<OpenApiDemoPathGet>();
    expectTypeOf<OpenApiResetOp>().toEqualTypeOf<OpenApiResetPathDelete>();
    type StateNeverBody = OpenApiStateOp extends { requestBody?: never } ? true : false;
    type FirstRunNeverBody = OpenApiFirstRunOp extends { requestBody?: never } ? true : false;
    type DemoNeverBody = OpenApiDemoOp extends { requestBody?: never } ? true : false;
    type ResetNeverBody = OpenApiResetOp extends { requestBody?: never } ? true : false;
    type StateHas201 = 201 extends keyof OpenApiStateOp['responses'] ? true : false;
    type PlanHas201 = 201 extends keyof OpenApiPlanOp['responses'] ? true : false;
    type ApplyHas201 = 201 extends keyof OpenApiApplyOp['responses'] ? true : false;
    type FirstRunHas201 = 201 extends keyof OpenApiFirstRunOp['responses'] ? true : false;
    type DemoHas201 = 201 extends keyof OpenApiDemoOp['responses'] ? true : false;
    type ResetHas201 = 201 extends keyof OpenApiResetOp['responses'] ? true : false;
    expectTypeOf<StateNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<FirstRunNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<DemoNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ResetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<StateHas201>().toEqualTypeOf<false>();
    expectTypeOf<PlanHas201>().toEqualTypeOf<false>();
    expectTypeOf<ApplyHas201>().toEqualTypeOf<false>();
    expectTypeOf<FirstRunHas201>().toEqualTypeOf<false>();
    expectTypeOf<DemoHas201>().toEqualTypeOf<false>();
    expectTypeOf<ResetHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public Override types equal path 200 JSON', () => {
    type PublicPlanExtendsPath = OnboardingPlan extends OpenApiPlanPost200 ? true : false;
    type PathExtendsPublicPlan = OpenApiPlanPost200 extends OnboardingPlan ? true : false;
    type PublicFirstRunExtendsPath = FirstRunReadiness extends OpenApiFirstRunGet200 ? true : false;
    type PathExtendsPublicFirstRun = OpenApiFirstRunGet200 extends FirstRunReadiness ? true : false;
    type PublicDemoExtendsPath = DemoAnalysisPayload extends OpenApiDemoGet200 ? true : false;
    type PathExtendsPublicDemo = OpenApiDemoGet200 extends DemoAnalysisPayload ? true : false;
    type PublicStateExtendsPath = OnboardingState extends OpenApiStateGet200 ? true : false;
    type PathExtendsPublicState = OpenApiStateGet200 extends OnboardingState ? true : false;
    type PublicApplyExtendsPath = OnboardingApplyResult extends OpenApiApplyPost200 ? true : false;
    type PathExtendsPublicApply = OpenApiApplyPost200 extends OnboardingApplyResult ? true : false;
    expectTypeOf<PublicPlanExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicPlan>().toEqualTypeOf<false>();
    expectTypeOf<PublicFirstRunExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicFirstRun>().toEqualTypeOf<false>();
    expectTypeOf<PublicDemoExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicDemo>().toEqualTypeOf<false>();
    expectTypeOf<PublicStateExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicState>().toEqualTypeOf<false>();
    expectTypeOf<PublicApplyExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicApply>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof OnboardingPlan>().not.toMatchTypeOf<'schema_version' | 'llm_note' | 'feature_path'>();
    expectTypeOf<keyof OnboardingApplyResult>().not.toMatchTypeOf<'applied_keys'>();
    expectTypeOf<keyof FirstRunReadiness>().not.toMatchTypeOf<'reason_params'>();
    expectTypeOf<keyof OpenApiPlan>().not.toMatchTypeOf<'schemaVersion' | 'llmNote' | 'featurePath'>();
    expectTypeOf<keyof OpenApiApply>().not.toMatchTypeOf<'appliedKeys'>();
    expectTypeOf<keyof OpenApiFirstRun>().not.toMatchTypeOf<'reasonParams'>();
  });

  it('keeps UI plan collections required while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(planMissingCollections).not.toMatchTypeOf<OnboardingPlan>();
    expectTypeOf(planMissingCollections).toMatchTypeOf<CamelizeKeys<OpenApiPlan>>();
    type UiTodosOptional = IsOptional<OnboardingPlan, 'todos'>;
    type UiChangesOptional = IsOptional<OnboardingPlan, 'configChanges'>;
    type NaiveTodosOptional = IsOptional<CamelizeKeys<OpenApiPlan>, 'todos'>;
    expectTypeOf<UiTodosOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiChangesOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveTodosOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI FeaturePath arrays required while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(shortFeature).not.toMatchTypeOf<OnboardingFeaturePath>();
    expectTypeOf(shortFeature).toMatchTypeOf<CamelizeKeys<OpenApiFeaturePath>>();
  });

  it('keeps UI first-run bags and runtime models required while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(firstRunMissingBags).not.toMatchTypeOf<FirstRunReadiness>();
    expectTypeOf(firstRunMissingBags).toMatchTypeOf<CamelizeKeys<OpenApiFirstRun>>();
    expectTypeOf(runtimeMissingModels).not.toMatchTypeOf<LocalRuntimeSnapshot>();
    expectTypeOf(runtimeMissingModels).toMatchTypeOf<CamelizeKeys<OpenApiRuntime>>();
  });

  it('keeps UI appliedKeys required on apply and state while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(applyMissingKeys).not.toMatchTypeOf<OnboardingApplyResult>();
    expectTypeOf(applyMissingKeys).toMatchTypeOf<CamelizeKeys<OpenApiApply>>();
    expectTypeOf({ exists: true }).not.toMatchTypeOf<OnboardingState>();
    expectTypeOf({ exists: true }).toMatchTypeOf<CamelizeKeys<OpenApiState>>();
  });

  it('assigns DEFAULT_ONBOARDING_PROFILE to UI plan.profile and not to naive generated plan.profile', () => {
    expectTypeOf(DEFAULT_ONBOARDING_PROFILE).toMatchTypeOf<OnboardingPlan['profile']>();
    expectTypeOf(DEFAULT_ONBOARDING_PROFILE).toMatchTypeOf<UserOnboardingProfile>();
    expectTypeOf(planBase).toMatchTypeOf<OnboardingPlan>();
    expectTypeOf(closedProfile).not.toMatchTypeOf<NaivePlanProfile>();
  });

  it("rejects 'not-a-stage' on UI experienceStage while naive CamelizeKeys accepts string", () => {
    expectTypeOf(badStage).not.toMatchTypeOf<UserOnboardingProfile>();
    expectTypeOf(badStage).toMatchTypeOf<CamelizeKeys<OpenApiProfile>>();
    expectTypeOf<'not-a-stage'>().not.toMatchTypeOf<UserOnboardingProfile['experienceStage']>();
    expectTypeOf<'not-a-stage'>().toMatchTypeOf<CamelizeKeys<OpenApiProfile>['experienceStage']>();
  });
});
