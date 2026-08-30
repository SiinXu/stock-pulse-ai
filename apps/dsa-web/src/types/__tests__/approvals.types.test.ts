// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as Approvals from '../approvals';
import type {
  ApprovalContext,
  ApprovalDecision,
  ApprovalProposal,
  ApprovalProposalPage,
  ApprovalRiskSource,
  ApprovalRule,
  ApprovalRuleUpdate,
  ApprovalStatus,
} from '../approvals';

type OpenApiContext = components['schemas']['ApprovalContext'];
type OpenApiProposal = components['schemas']['ApprovalProposal'];
type OpenApiPage = components['schemas']['ApprovalProposalPage'];
type OpenApiRule = components['schemas']['ApprovalRule'];
type OpenApiRuleUpdate = components['schemas']['ApprovalRuleUpdateRequest'];
type OpenApiDecisionRequest = components['schemas']['ApprovalDecisionRequest'];
type OpenApiList200 =
  operations['list_approvals_api_v1_approvals_get']['responses']['200']['content']['application/json'];
type OpenApiGetRule200 =
  operations['get_risk_control_bypass_rule_api_v1_approvals_rules_risk_control_bypass_get']['responses']['200']['content']['application/json'];
type OpenApiPutRule200 =
  operations['put_risk_control_bypass_rule_api_v1_approvals_rules_risk_control_bypass_put']['responses']['200']['content']['application/json'];
type OpenApiPutRuleBody =
  operations['put_risk_control_bypass_rule_api_v1_approvals_rules_risk_control_bypass_put']['requestBody']['content']['application/json'];
type OpenApiGetProposal200 =
  operations['get_approval_api_v1_approvals__proposal_id__get']['responses']['200']['content']['application/json'];
type OpenApiDecide200 =
  operations['decide_approval_api_v1_approvals__proposal_id__decision_post']['responses']['200']['content']['application/json'];
type OpenApiDecideBody =
  operations['decide_approval_api_v1_approvals__proposal_id__decision_post']['requestBody']['content']['application/json'];

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _List200IsPage = _Assert<OpenApiList200 extends OpenApiPage ? true : false>;
type _PageIsList200 = _Assert<OpenApiPage extends OpenApiList200 ? true : false>;
type _GetRule200IsRule = _Assert<OpenApiGetRule200 extends OpenApiRule ? true : false>;
type _RuleIsGetRule200 = _Assert<OpenApiRule extends OpenApiGetRule200 ? true : false>;
type _PutRule200IsRule = _Assert<OpenApiPutRule200 extends OpenApiRule ? true : false>;
type _RuleIsPutRule200 = _Assert<OpenApiRule extends OpenApiPutRule200 ? true : false>;
type _PutBodyIsUpdate = _Assert<OpenApiPutRuleBody extends OpenApiRuleUpdate ? true : false>;
type _UpdateIsPutBody = _Assert<OpenApiRuleUpdate extends OpenApiPutRuleBody ? true : false>;
type _GetProposal200IsProposal = _Assert<OpenApiGetProposal200 extends OpenApiProposal ? true : false>;
type _ProposalIsGetProposal200 = _Assert<OpenApiProposal extends OpenApiGetProposal200 ? true : false>;
type _Decide200IsProposal = _Assert<OpenApiDecide200 extends OpenApiProposal ? true : false>;
type _ProposalIsDecide200 = _Assert<OpenApiProposal extends OpenApiDecide200 ? true : false>;
type _DecideBodyIsRequest = _Assert<OpenApiDecideBody extends OpenApiDecisionRequest ? true : false>;
type _RequestIsDecideBody = _Assert<OpenApiDecisionRequest extends OpenApiDecideBody ? true : false>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof ApprovalContext ? true : false>;
type _UiHasOriginalSignal = _Assert<'originalSignal' extends keyof ApprovalContext ? true : false>;
type _UiHasConservativeSignal = _Assert<'conservativeSignal' extends keyof ApprovalContext ? true : false>;
type _UiHasRiskSource = _Assert<'riskSource' extends keyof ApprovalContext ? true : false>;
type _UiHasRiskSummary = _Assert<'riskSummary' extends keyof ApprovalContext ? true : false>;
type _UiHasExpiresAt = _Assert<'expiresAt' extends keyof ApprovalProposal ? true : false>;
type _UiHasConsumedAt = _Assert<'consumedAt' extends keyof ApprovalProposal ? true : false>;
type _UiHasPageSize = _Assert<'pageSize' extends keyof ApprovalProposalPage ? true : false>;
type _UiHasExpiresInSeconds = _Assert<'expiresInSeconds' extends keyof ApprovalRule ? true : false>;
type _UiHasRiskSources = _Assert<'riskSources' extends keyof ApprovalRule ? true : false>;
type _UiHasUpdatedAt = _Assert<'updatedAt' extends keyof ApprovalRule ? true : false>;
type _UiHasExpectedVersion = _Assert<'expectedVersion' extends keyof ApprovalRuleUpdate ? true : false>;
type _UiUpdateHasExpiresInSeconds = _Assert<'expiresInSeconds' extends keyof ApprovalRuleUpdate ? true : false>;
type _UiUpdateHasRiskSources = _Assert<'riskSources' extends keyof ApprovalRuleUpdate ? true : false>;

type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof ApprovalContext ? false : true>;
type _UiLacksOriginalSignalSnake = _Assert<'original_signal' extends keyof ApprovalContext ? false : true>;
type _UiLacksConservativeSignalSnake = _Assert<'conservative_signal' extends keyof ApprovalContext ? false : true>;
type _UiLacksRiskSourceSnake = _Assert<'risk_source' extends keyof ApprovalContext ? false : true>;
type _UiLacksRiskSummarySnake = _Assert<'risk_summary' extends keyof ApprovalContext ? false : true>;
type _UiLacksExpiresAtSnake = _Assert<'expires_at' extends keyof ApprovalProposal ? false : true>;
type _UiLacksConsumedAtSnake = _Assert<'consumed_at' extends keyof ApprovalProposal ? false : true>;
type _UiLacksPageSizeSnake = _Assert<'page_size' extends keyof ApprovalProposalPage ? false : true>;
type _UiLacksExpiresInSecondsSnake = _Assert<'expires_in_seconds' extends keyof ApprovalRule ? false : true>;
type _UiLacksRiskSourcesSnake = _Assert<'risk_sources' extends keyof ApprovalRule ? false : true>;
type _UiLacksUpdatedAtSnake = _Assert<'updated_at' extends keyof ApprovalRule ? false : true>;
type _UiLacksExpectedVersionSnake = _Assert<'expected_version' extends keyof ApprovalRuleUpdate ? false : true>;
type _UiUpdateLacksExpiresInSecondsSnake = _Assert<'expires_in_seconds' extends keyof ApprovalRuleUpdate ? false : true>;
type _UiUpdateLacksRiskSourcesSnake = _Assert<'risk_sources' extends keyof ApprovalRuleUpdate ? false : true>;

type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiContext ? true : false>;
type _GeneratedHasOriginalSignalSnake = _Assert<'original_signal' extends keyof OpenApiContext ? true : false>;
type _GeneratedHasConservativeSignalSnake = _Assert<'conservative_signal' extends keyof OpenApiContext ? true : false>;
type _GeneratedHasRiskSourceSnake = _Assert<'risk_source' extends keyof OpenApiContext ? true : false>;
type _GeneratedHasRiskSummarySnake = _Assert<'risk_summary' extends keyof OpenApiContext ? true : false>;
type _GeneratedHasExpiresAtSnake = _Assert<'expires_at' extends keyof OpenApiProposal ? true : false>;
type _GeneratedHasConsumedAtSnake = _Assert<'consumed_at' extends keyof OpenApiProposal ? true : false>;
type _GeneratedHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiPage ? true : false>;
type _GeneratedHasExpiresInSecondsSnake = _Assert<'expires_in_seconds' extends keyof OpenApiRule ? true : false>;
type _GeneratedHasRiskSourcesSnake = _Assert<'risk_sources' extends keyof OpenApiRule ? true : false>;
type _GeneratedHasUpdatedAtSnake = _Assert<'updated_at' extends keyof OpenApiRule ? true : false>;
type _GeneratedUpdateHasExpiresInSecondsSnake = _Assert<'expires_in_seconds' extends keyof OpenApiRuleUpdate ? true : false>;
type _GeneratedUpdateHasRiskSourcesSnake = _Assert<'risk_sources' extends keyof OpenApiRuleUpdate ? true : false>;

type _GeneratedHasExpectedVersion = _Assert<'expectedVersion' extends keyof OpenApiRuleUpdate ? true : false>;
type _GeneratedLacksExpectedVersionSnake = _Assert<'expected_version' extends keyof OpenApiRuleUpdate ? false : true>;
type _GeneratedLacksExpiresInSecondsCamel = _Assert<'expiresInSeconds' extends keyof OpenApiRuleUpdate ? false : true>;
type _DecisionHasExpectedVersion = _Assert<'expectedVersion' extends keyof OpenApiDecisionRequest ? true : false>;
type _DecisionLacksExpectedVersionSnake = _Assert<'expected_version' extends keyof OpenApiDecisionRequest ? false : true>;

type _UiStockCodeOptional = _Assert<IsOptional<ApprovalContext, 'stockCode'>>;
type _GeneratedStockCodeRequired = _Assert<IsOptional<OpenApiContext, 'stock_code'> extends false ? true : false>;
type _UiActionOptional = _Assert<IsOptional<ApprovalRule, 'action'>>;
type _GeneratedActionRequired = _Assert<IsOptional<OpenApiRule, 'action'> extends false ? true : false>;
type _UiConsumedAtOptional = _Assert<IsOptional<ApprovalProposal, 'consumedAt'>>;
type _UiUpdatedAtOptional = _Assert<IsOptional<ApprovalRule, 'updatedAt'>>;

type _OmitUiStockCodeMatches = _Assert<Omit<ApprovalContext, 'stockCode'> extends ApprovalContext ? true : false>;
type _OmitGeneratedStockCodeDoesNotMatch = _Assert<
  Omit<OpenApiContext, 'stock_code'> extends OpenApiContext ? false : true
>;
type _OmitUiActionMatches = _Assert<Omit<ApprovalRule, 'action'> extends ApprovalRule ? true : false>;
type _OmitGeneratedActionDoesNotMatch = _Assert<Omit<OpenApiRule, 'action'> extends OpenApiRule ? false : true>;

type NarrowContext = {
  originalSignal: 'buy';
  conservativeSignal: 'hold';
  riskSource: 'risk_veto';
  riskSummary: string;
};
type NarrowRule = {
  owner: string;
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  version: number;
  updatedAt: null;
};
type NarrowProposal = {
  id: string;
  owner: string;
  status: 'pending';
  version: number;
  expiresAt: string;
  consumedAt: null;
  context: NarrowContext;
};
type NarrowPage = {
  items: NarrowProposal[];
  page: number;
  pageSize: number;
  total: number;
};
type NarrowRuleUpdate = {
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  expectedVersion: number;
};

type _NarrowContextAssignable = _Assert<NarrowContext extends ApprovalContext ? true : false>;
type _NarrowRuleAssignable = _Assert<NarrowRule extends ApprovalRule ? true : false>;
type _NarrowProposalAssignable = _Assert<NarrowProposal extends ApprovalProposal ? true : false>;
type _NarrowPageAssignable = _Assert<NarrowPage extends ApprovalProposalPage ? true : false>;
type _NarrowRuleUpdateAssignable = _Assert<NarrowRuleUpdate extends ApprovalRuleUpdate ? true : false>;

type SnakeContext = {
  stock_code: string;
  original_signal: 'buy';
  conservative_signal: 'hold';
  risk_source: 'risk_veto';
  risk_summary: string;
};
type SnakeProposal = {
  id: string;
  owner: string;
  status: 'pending';
  version: number;
  expires_at: string;
  consumed_at: null;
  context: SnakeContext;
};
type SnakePage = {
  items: SnakeProposal[];
  page: number;
  page_size: number;
  total: number;
};
type _SnakeContextMatchesGenerated = _Assert<SnakeContext extends OpenApiContext ? true : false>;
type _SnakeContextDoesNotMatchUi = _Assert<SnakeContext extends ApprovalContext ? false : true>;
type _SnakeProposalMatchesGenerated = _Assert<SnakeProposal extends OpenApiProposal ? true : false>;
type _SnakeProposalDoesNotMatchUi = _Assert<SnakeProposal extends ApprovalProposal ? false : true>;
type _SnakePageMatchesGenerated = _Assert<SnakePage extends OpenApiPage ? true : false>;
type _SnakePageDoesNotMatchUi = _Assert<SnakePage extends ApprovalProposalPage ? false : true>;

type BuyContext = {
  originalSignal: 'buy';
  conservativeSignal: 'hold';
  riskSource: 'risk_veto';
  riskSummary: string;
};
type MoonshotContext = {
  originalSignal: 'moonshot';
  conservativeSignal: 'hold';
  riskSource: 'risk_veto';
  riskSummary: string;
};
type CustomRiskContext = {
  originalSignal: 'buy';
  conservativeSignal: 'hold';
  riskSource: 'custom_risk';
  riskSummary: string;
};
type MysteryStatusProposal = {
  id: string;
  owner: string;
  status: 'mystery_status';
  version: number;
  expiresAt: string;
  consumedAt: null;
  context: BuyContext;
};
type OtherActionRule = {
  owner: string;
  action: 'other';
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  version: number;
  updatedAt: null;
};
type BypassActionRule = {
  owner: string;
  action: 'risk_control_bypass';
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  version: number;
  updatedAt: null;
};

type _BuyContextAssignable = _Assert<BuyContext extends ApprovalContext ? true : false>;
type _MoonshotContextRejected = _Assert<MoonshotContext extends ApprovalContext ? false : true>;
type _CustomRiskContextRejected = _Assert<CustomRiskContext extends ApprovalContext ? false : true>;
type _MysteryStatusRejected = _Assert<MysteryStatusProposal extends ApprovalProposal ? false : true>;
type _MaybeDecisionRejected = _Assert<'maybe' extends ApprovalDecision ? false : true>;
type _ApprovedDecisionAssignable = _Assert<'approved' extends ApprovalDecision ? true : false>;
type _OtherActionAssignable = _Assert<OtherActionRule extends ApprovalRule ? true : false>;
type _BypassActionAssignable = _Assert<BypassActionRule extends ApprovalRule ? true : false>;
type _PendingStatusAssignable = _Assert<'pending' extends ApprovalStatus ? true : false>;
type _VetoRiskAssignable = _Assert<'risk_veto' extends ApprovalRiskSource ? true : false>;

type _CompileTimePins = [
  _List200IsPage,
  _PageIsList200,
  _GetRule200IsRule,
  _RuleIsGetRule200,
  _PutRule200IsRule,
  _RuleIsPutRule200,
  _PutBodyIsUpdate,
  _UpdateIsPutBody,
  _GetProposal200IsProposal,
  _ProposalIsGetProposal200,
  _Decide200IsProposal,
  _ProposalIsDecide200,
  _DecideBodyIsRequest,
  _RequestIsDecideBody,
  _UiHasStockCode,
  _UiHasOriginalSignal,
  _UiHasConservativeSignal,
  _UiHasRiskSource,
  _UiHasRiskSummary,
  _UiHasExpiresAt,
  _UiHasConsumedAt,
  _UiHasPageSize,
  _UiHasExpiresInSeconds,
  _UiHasRiskSources,
  _UiHasUpdatedAt,
  _UiHasExpectedVersion,
  _UiUpdateHasExpiresInSeconds,
  _UiUpdateHasRiskSources,
  _UiLacksStockCodeSnake,
  _UiLacksOriginalSignalSnake,
  _UiLacksConservativeSignalSnake,
  _UiLacksRiskSourceSnake,
  _UiLacksRiskSummarySnake,
  _UiLacksExpiresAtSnake,
  _UiLacksConsumedAtSnake,
  _UiLacksPageSizeSnake,
  _UiLacksExpiresInSecondsSnake,
  _UiLacksRiskSourcesSnake,
  _UiLacksUpdatedAtSnake,
  _UiLacksExpectedVersionSnake,
  _UiUpdateLacksExpiresInSecondsSnake,
  _UiUpdateLacksRiskSourcesSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasOriginalSignalSnake,
  _GeneratedHasConservativeSignalSnake,
  _GeneratedHasRiskSourceSnake,
  _GeneratedHasRiskSummarySnake,
  _GeneratedHasExpiresAtSnake,
  _GeneratedHasConsumedAtSnake,
  _GeneratedHasPageSizeSnake,
  _GeneratedHasExpiresInSecondsSnake,
  _GeneratedHasRiskSourcesSnake,
  _GeneratedHasUpdatedAtSnake,
  _GeneratedUpdateHasExpiresInSecondsSnake,
  _GeneratedUpdateHasRiskSourcesSnake,
  _GeneratedHasExpectedVersion,
  _GeneratedLacksExpectedVersionSnake,
  _GeneratedLacksExpiresInSecondsCamel,
  _DecisionHasExpectedVersion,
  _DecisionLacksExpectedVersionSnake,
  _UiStockCodeOptional,
  _GeneratedStockCodeRequired,
  _UiActionOptional,
  _GeneratedActionRequired,
  _UiConsumedAtOptional,
  _UiUpdatedAtOptional,
  _OmitUiStockCodeMatches,
  _OmitGeneratedStockCodeDoesNotMatch,
  _OmitUiActionMatches,
  _OmitGeneratedActionDoesNotMatch,
  _NarrowContextAssignable,
  _NarrowRuleAssignable,
  _NarrowProposalAssignable,
  _NarrowPageAssignable,
  _NarrowRuleUpdateAssignable,
  _SnakeContextMatchesGenerated,
  _SnakeContextDoesNotMatchUi,
  _SnakeProposalMatchesGenerated,
  _SnakeProposalDoesNotMatchUi,
  _SnakePageMatchesGenerated,
  _SnakePageDoesNotMatchUi,
  _BuyContextAssignable,
  _MoonshotContextRejected,
  _CustomRiskContextRejected,
  _MysteryStatusRejected,
  _MaybeDecisionRejected,
  _ApprovedDecisionAssignable,
  _OtherActionAssignable,
  _BypassActionAssignable,
  _PendingStatusAssignable,
  _VetoRiskAssignable,
];

const CONTEXT_REST = {
  conservativeSignal: 'hold' as const,
  riskSource: 'risk_veto' as const,
  riskSummary: 'veto',
};

const RULE_REST = {
  owner: 'admin',
  enabled: true,
  riskSources: ['risk_veto'] as ApprovalRiskSource[],
  expiresInSeconds: 3600,
  version: 1,
  updatedAt: null as string | null,
};

describe('approvals OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Approvals }).toEqual({});
    expect(Object.keys(Approvals)).toEqual([]);
    expect(Object.getOwnPropertyNames(Approvals)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON and request bodies to the generated components', () => {
    expectTypeOf<OpenApiList200>().toEqualTypeOf<OpenApiPage>();
    expectTypeOf<OpenApiGetRule200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiPutRule200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiPutRuleBody>().toEqualTypeOf<OpenApiRuleUpdate>();
    expectTypeOf<OpenApiGetProposal200>().toEqualTypeOf<OpenApiProposal>();
    expectTypeOf<OpenApiDecide200>().toEqualTypeOf<OpenApiProposal>();
    expectTypeOf<OpenApiDecideBody>().toEqualTypeOf<OpenApiDecisionRequest>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof ApprovalContext>().not.toMatchTypeOf<
      'stock_code' | 'original_signal' | 'conservative_signal' | 'risk_source' | 'risk_summary'
    >();
    expectTypeOf<keyof ApprovalProposal>().not.toMatchTypeOf<'expires_at' | 'consumed_at'>();
    expectTypeOf<keyof ApprovalProposalPage>().not.toMatchTypeOf<'page_size'>();
    expectTypeOf<keyof ApprovalRule>().not.toMatchTypeOf<
      'expires_in_seconds' | 'risk_sources' | 'updated_at'
    >();
    expectTypeOf<keyof ApprovalRuleUpdate>().not.toMatchTypeOf<
      'expected_version' | 'expires_in_seconds' | 'risk_sources'
    >();

    type UiHasStockCode = 'stockCode' extends keyof ApprovalContext ? true : false;
    type UiHasStockCodeSnake = 'stock_code' extends keyof ApprovalContext ? true : false;
    type GeneratedHasStockCodeSnake = 'stock_code' extends keyof OpenApiContext ? true : false;
    type UiHasOriginalSignal = 'originalSignal' extends keyof ApprovalContext ? true : false;
    type UiHasOriginalSignalSnake = 'original_signal' extends keyof ApprovalContext ? true : false;
    type GeneratedHasOriginalSignalSnake = 'original_signal' extends keyof OpenApiContext ? true : false;
    type UiHasConservativeSignal = 'conservativeSignal' extends keyof ApprovalContext ? true : false;
    type UiHasConservativeSignalSnake = 'conservative_signal' extends keyof ApprovalContext ? true : false;
    type GeneratedHasConservativeSignalSnake = 'conservative_signal' extends keyof OpenApiContext ? true : false;
    type UiHasRiskSource = 'riskSource' extends keyof ApprovalContext ? true : false;
    type UiHasRiskSourceSnake = 'risk_source' extends keyof ApprovalContext ? true : false;
    type GeneratedHasRiskSourceSnake = 'risk_source' extends keyof OpenApiContext ? true : false;
    type UiHasRiskSummary = 'riskSummary' extends keyof ApprovalContext ? true : false;
    type UiHasRiskSummarySnake = 'risk_summary' extends keyof ApprovalContext ? true : false;
    type GeneratedHasRiskSummarySnake = 'risk_summary' extends keyof OpenApiContext ? true : false;
    type UiHasExpiresAt = 'expiresAt' extends keyof ApprovalProposal ? true : false;
    type UiHasExpiresAtSnake = 'expires_at' extends keyof ApprovalProposal ? true : false;
    type GeneratedHasExpiresAtSnake = 'expires_at' extends keyof OpenApiProposal ? true : false;
    type UiHasConsumedAt = 'consumedAt' extends keyof ApprovalProposal ? true : false;
    type UiHasConsumedAtSnake = 'consumed_at' extends keyof ApprovalProposal ? true : false;
    type GeneratedHasConsumedAtSnake = 'consumed_at' extends keyof OpenApiProposal ? true : false;
    type UiHasPageSize = 'pageSize' extends keyof ApprovalProposalPage ? true : false;
    type UiHasPageSizeSnake = 'page_size' extends keyof ApprovalProposalPage ? true : false;
    type GeneratedHasPageSizeSnake = 'page_size' extends keyof OpenApiPage ? true : false;
    type UiHasExpiresInSeconds = 'expiresInSeconds' extends keyof ApprovalRule ? true : false;
    type UiHasExpiresInSecondsSnake = 'expires_in_seconds' extends keyof ApprovalRule ? true : false;
    type GeneratedHasExpiresInSecondsSnake = 'expires_in_seconds' extends keyof OpenApiRule ? true : false;
    type UiHasRiskSources = 'riskSources' extends keyof ApprovalRule ? true : false;
    type UiHasRiskSourcesSnake = 'risk_sources' extends keyof ApprovalRule ? true : false;
    type GeneratedHasRiskSourcesSnake = 'risk_sources' extends keyof OpenApiRule ? true : false;
    type UiHasUpdatedAt = 'updatedAt' extends keyof ApprovalRule ? true : false;
    type UiHasUpdatedAtSnake = 'updated_at' extends keyof ApprovalRule ? true : false;
    type GeneratedHasUpdatedAtSnake = 'updated_at' extends keyof OpenApiRule ? true : false;

    expectTypeOf<UiHasStockCode>().toEqualTypeOf<true>();
    expectTypeOf<UiHasStockCodeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasStockCodeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasOriginalSignal>().toEqualTypeOf<true>();
    expectTypeOf<UiHasOriginalSignalSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasOriginalSignalSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasConservativeSignal>().toEqualTypeOf<true>();
    expectTypeOf<UiHasConservativeSignalSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasConservativeSignalSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSource>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSourceSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRiskSourceSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSummary>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSummarySnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRiskSummarySnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpiresAt>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpiresAtSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasExpiresAtSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasConsumedAt>().toEqualTypeOf<true>();
    expectTypeOf<UiHasConsumedAtSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasConsumedAtSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSize>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSizeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPageSizeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpiresInSeconds>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpiresInSecondsSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasExpiresInSecondsSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSources>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSourcesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRiskSourcesSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasUpdatedAt>().toEqualTypeOf<true>();
    expectTypeOf<UiHasUpdatedAtSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasUpdatedAtSnake>().toEqualTypeOf<true>();
  });

  it('pins mixed-alias expectedVersion on generated request schemas', () => {
    type GeneratedHasExpectedVersion = 'expectedVersion' extends keyof OpenApiRuleUpdate ? true : false;
    type GeneratedHasExpectedVersionSnake = 'expected_version' extends keyof OpenApiRuleUpdate ? true : false;
    type GeneratedHasExpiresInSecondsSnake = 'expires_in_seconds' extends keyof OpenApiRuleUpdate ? true : false;
    type GeneratedHasExpiresInSecondsCamel = 'expiresInSeconds' extends keyof OpenApiRuleUpdate ? true : false;
    type UiHasExpectedVersion = 'expectedVersion' extends keyof ApprovalRuleUpdate ? true : false;
    type UiHasExpiresInSeconds = 'expiresInSeconds' extends keyof ApprovalRuleUpdate ? true : false;
    type UiHasRiskSources = 'riskSources' extends keyof ApprovalRuleUpdate ? true : false;
    type UiHasExpectedVersionSnake = 'expected_version' extends keyof ApprovalRuleUpdate ? true : false;
    type DecisionHasExpectedVersion = 'expectedVersion' extends keyof OpenApiDecisionRequest ? true : false;
    type DecisionHasExpectedVersionSnake = 'expected_version' extends keyof OpenApiDecisionRequest ? true : false;

    expectTypeOf<GeneratedHasExpectedVersion>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasExpectedVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasExpiresInSecondsSnake>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasExpiresInSecondsCamel>().toEqualTypeOf<false>();
    expectTypeOf<UiHasExpectedVersion>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpiresInSeconds>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskSources>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExpectedVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<DecisionHasExpectedVersion>().toEqualTypeOf<true>();
    expectTypeOf<DecisionHasExpectedVersionSnake>().toEqualTypeOf<false>();
  });

  it('keeps UI stockCode and action optional while generated counterparts stay required', () => {
    expectTypeOf<Omit<ApprovalContext, 'stockCode'>>().toMatchTypeOf<ApprovalContext>();
    expectTypeOf<Omit<OpenApiContext, 'stock_code'>>().not.toMatchTypeOf<OpenApiContext>();
    expectTypeOf<Omit<ApprovalRule, 'action'>>().toMatchTypeOf<ApprovalRule>();
    expectTypeOf<Omit<OpenApiRule, 'action'>>().not.toMatchTypeOf<OpenApiRule>();
  });

  it('keeps signal, status, decision, and risk-source unions closed while widening optional action', () => {
    expectTypeOf({ originalSignal: 'buy' as const, ...CONTEXT_REST }).toMatchTypeOf<ApprovalContext>();
    expectTypeOf({ originalSignal: 'moonshot' as const, ...CONTEXT_REST }).not.toMatchTypeOf<ApprovalContext>();
    expectTypeOf({
      originalSignal: 'buy' as const,
      conservativeSignal: 'hold' as const,
      riskSource: 'custom_risk' as const,
      riskSummary: 'veto',
    }).not.toMatchTypeOf<ApprovalContext>();
    expectTypeOf({
      id: 'p1',
      owner: 'admin',
      status: 'mystery_status' as const,
      version: 1,
      expiresAt: '2026-08-30T12:00:00Z',
      consumedAt: null,
      context: { originalSignal: 'buy' as const, ...CONTEXT_REST },
    }).not.toMatchTypeOf<ApprovalProposal>();
    expectTypeOf<'maybe'>().not.toMatchTypeOf<ApprovalDecision>();
    expectTypeOf<'approved'>().toMatchTypeOf<ApprovalDecision>();
    expectTypeOf({ action: 'other', ...RULE_REST }).toMatchTypeOf<ApprovalRule>();
    expectTypeOf({ action: 'risk_control_bypass' as const, ...RULE_REST }).toMatchTypeOf<ApprovalRule>();
  });

  it('still accepts the narrow existing context, rule, proposal, page, and update fixtures', () => {
    const context = {
      originalSignal: 'buy' as const,
      conservativeSignal: 'hold' as const,
      riskSource: 'risk_veto' as const,
      riskSummary: 'veto',
    };
    const rule = {
      owner: 'admin',
      enabled: true,
      riskSources: ['risk_veto'] as ApprovalRiskSource[],
      expiresInSeconds: 3600,
      version: 1,
      updatedAt: null,
    };
    const proposal = {
      id: 'p1',
      owner: 'admin',
      status: 'pending' as const,
      version: 1,
      expiresAt: '2026-08-30T12:00:00Z',
      consumedAt: null,
      context,
    };
    const page = {
      items: [proposal],
      page: 1,
      pageSize: 20,
      total: 1,
    };
    const update = {
      enabled: true,
      riskSources: ['risk_downgrade'] as ApprovalRiskSource[],
      expiresInSeconds: 120,
      expectedVersion: 3,
    };
    expectTypeOf(context).toMatchTypeOf<ApprovalContext>();
    expectTypeOf(rule).toMatchTypeOf<ApprovalRule>();
    expectTypeOf(proposal).toMatchTypeOf<ApprovalProposal>();
    expectTypeOf(page).toMatchTypeOf<ApprovalProposalPage>();
    expectTypeOf(update).toMatchTypeOf<ApprovalRuleUpdate>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeContext = {
      stock_code: '600519',
      original_signal: 'buy' as const,
      conservative_signal: 'hold' as const,
      risk_source: 'risk_veto' as const,
      risk_summary: 'veto',
    };
    const snakeProposal = {
      id: 'p1',
      owner: 'admin',
      status: 'pending' as const,
      version: 1,
      expires_at: '2026-08-30T12:00:00Z',
      consumed_at: null,
      context: snakeContext,
    };
    const snakePage = {
      items: [snakeProposal],
      page: 1,
      page_size: 20,
      total: 1,
    };
    expectTypeOf(snakeContext).toMatchTypeOf<OpenApiContext>();
    expectTypeOf(snakeContext).not.toMatchTypeOf<ApprovalContext>();
    expectTypeOf(snakeProposal).toMatchTypeOf<OpenApiProposal>();
    expectTypeOf(snakeProposal).not.toMatchTypeOf<ApprovalProposal>();
    expectTypeOf(snakePage).toMatchTypeOf<OpenApiPage>();
    expectTypeOf(snakePage).not.toMatchTypeOf<ApprovalProposalPage>();
  });
});
