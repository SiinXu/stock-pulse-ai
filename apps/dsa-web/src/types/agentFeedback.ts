// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiAgentRunFeedbackItem = components['schemas']['AgentRunFeedbackItem'];
type OpenApiAgentRunFeedbackRequest = components['schemas']['AgentRunFeedbackRequest'];
type OpenApiGetOp = operations['getAgentRunFeedback'];
type OpenApiPutOp = operations['putAgentRunFeedback'];
type OpenApiPathGet = paths['/api/v1/agent/runs/{run_id}/feedback']['get'];
type OpenApiPathPut = paths['/api/v1/agent/runs/{run_id}/feedback']['put'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPut200 = OpenApiPutOp['responses']['200']['content']['application/json'];
type OpenApiPutBody = OpenApiPutOp['requestBody']['content']['application/json'];

type _Assert<T extends true> = T;
type _Get200IsItem = _Assert<OpenApiGet200 extends OpenApiAgentRunFeedbackItem ? true : false>;
type _ItemIsGet200 = _Assert<OpenApiAgentRunFeedbackItem extends OpenApiGet200 ? true : false>;
type _Put200IsItem = _Assert<OpenApiPut200 extends OpenApiAgentRunFeedbackItem ? true : false>;
type _ItemIsPut200 = _Assert<OpenApiAgentRunFeedbackItem extends OpenApiPut200 ? true : false>;
type _PutBodyIsRequest = _Assert<OpenApiPutBody extends OpenApiAgentRunFeedbackRequest ? true : false>;
type _RequestIsPutBody = _Assert<OpenApiAgentRunFeedbackRequest extends OpenApiPutBody ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _PutOpIsPath = _Assert<OpenApiPutOp extends OpenApiPathPut ? true : false>;
type _PathIsPutOp = _Assert<OpenApiPathPut extends OpenApiPutOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _GetQueryNever = _Assert<
  OpenApiGetOp['parameters']['query'] extends never | undefined ? true : false
>;
type _PutQueryNever = _Assert<
  OpenApiPutOp['parameters']['query'] extends never | undefined ? true : false
>;
type _GetPathRunIdIsString = _Assert<
  OpenApiGetOp['parameters']['path']['run_id'] extends string
    ? string extends OpenApiGetOp['parameters']['path']['run_id'] ? true : false
    : false
>;
type _PutPathRunIdIsString = _Assert<
  OpenApiPutOp['parameters']['path']['run_id'] extends string
    ? string extends OpenApiPutOp['parameters']['path']['run_id'] ? true : false
    : false
>;
type _PathPostNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['post'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['delete'] extends never | undefined ? true : false
>;
type _PathPatchNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['patch'] extends never | undefined ? true : false
>;

type _OpenApiAnchors = [
  _Get200IsItem,
  _ItemIsGet200,
  _Put200IsItem,
  _ItemIsPut200,
  _PutBodyIsRequest,
  _RequestIsPutBody,
  _GetOpIsPath,
  _PathIsGetOp,
  _PutOpIsPath,
  _PathIsPutOp,
  _GetOpHasNeverRequestBody,
  _GetQueryNever,
  _PutQueryNever,
  _GetPathRunIdIsString,
  _PutPathRunIdIsString,
  _PathPostNever,
  _PathDeleteNever,
  _PathPatchNever,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

type CamelItem = CamelizeKeys<OpenApiAgentRunFeedbackItem>;

export type AgentRunFeedbackValue = NonNullable<OpenApiAgentRunFeedbackItem['feedback_value']>;

export type AgentRunFeedbackItem = _BindOpenApiAnchors<Override<CamelItem, {
  feedbackValue: AgentRunFeedbackValue | null;
  note: string | null;
  source: NonNullable<CamelItem['source']> | null;
  provenanceSource: NonNullable<CamelItem['provenanceSource']> | null;
  actorId: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}>>;

export type AgentRunFeedbackRequest = {
  feedbackValue: AgentRunFeedbackValue;
  note: string;
  source: 'web';
};
