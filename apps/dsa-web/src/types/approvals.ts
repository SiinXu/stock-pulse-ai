// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

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

type _OpenApiAnchors = [
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
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type ApprovalRiskSource = components['schemas']['ApprovalRiskSource'];
export type ApprovalStatus = components['schemas']['ApprovalStatus'];
export type ApprovalDecision = components['schemas']['ApprovalDecision'];

export type ApprovalContext = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiContext>, {
  stockCode?: string;
  originalSignal: 'buy' | 'hold' | 'sell';
  conservativeSignal: 'buy' | 'hold' | 'sell';
  riskSource: ApprovalRiskSource;
  riskSummary: string;
}>>;

export type ApprovalRule = Override<CamelizeKeys<OpenApiRule>, {
  owner: string;
  action?: 'risk_control_bypass' | string;
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  version: number;
  updatedAt?: string | null;
}>;

export type ApprovalProposal = Override<CamelizeKeys<OpenApiProposal>, {
  id: string;
  owner: string;
  status: ApprovalStatus;
  version: number;
  expiresAt: string;
  consumedAt?: string | null;
  context: ApprovalContext;
}>;

export type ApprovalProposalPage = Override<CamelizeKeys<OpenApiPage>, {
  items: ApprovalProposal[];
  page: number;
  pageSize: number;
  total: number;
}>;

export type ApprovalRuleUpdate = Override<CamelizeKeys<OpenApiRuleUpdate>, {
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  expectedVersion: number;
}>;
