// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as AgentFeedback from '../agentFeedback';
import type {
  AgentRunFeedbackItem,
  AgentRunFeedbackRequest,
  AgentRunFeedbackValue,
} from '../agentFeedback';

type OpenApiItem = components['schemas']['AgentRunFeedbackItem'];
type OpenApiRequest = components['schemas']['AgentRunFeedbackRequest'];
type OpenApiGetOp = operations['getAgentRunFeedback'];
type OpenApiPutOp = operations['putAgentRunFeedback'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPut200 = OpenApiPutOp['responses']['200']['content']['application/json'];
type OpenApiPutBody = OpenApiPutOp['requestBody']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/agent/runs/{run_id}/feedback']['get'];
type OpenApiPathPut = paths['/api/v1/agent/runs/{run_id}/feedback']['put'];

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

type _TwoComponents = _Assert<
  ('AgentRunFeedbackItem' | 'AgentRunFeedbackRequest') extends keyof components['schemas'] ? true : false
>;
type _Get200IsItem = _Assert<OpenApiGet200 extends OpenApiItem ? true : false>;
type _ItemIsGet200 = _Assert<OpenApiItem extends OpenApiGet200 ? true : false>;
type _Put200IsItem = _Assert<OpenApiPut200 extends OpenApiItem ? true : false>;
type _ItemIsPut200 = _Assert<OpenApiItem extends OpenApiPut200 ? true : false>;
type _PutBodyIsRequest = _Assert<OpenApiPutBody extends OpenApiRequest ? true : false>;
type _RequestIsPutBody = _Assert<OpenApiRequest extends OpenApiPutBody ? true : false>;
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
type _PathPostNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['post'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['delete'] extends never | undefined ? true : false
>;
type _PathPatchNever = _Assert<
  paths['/api/v1/agent/runs/{run_id}/feedback']['patch'] extends never | undefined ? true : false
>;

type _UiHasRunId = _Assert<'runId' extends keyof AgentRunFeedbackItem ? true : false>;
type _UiHasFeedbackValue = _Assert<'feedbackValue' extends keyof AgentRunFeedbackItem ? true : false>;
type _UiHasProvenanceSource = _Assert<'provenanceSource' extends keyof AgentRunFeedbackItem ? true : false>;
type _UiLacksRunIdSnake = _Assert<'run_id' extends keyof AgentRunFeedbackItem ? false : true>;
type _UiLacksFeedbackValueSnake = _Assert<'feedback_value' extends keyof AgentRunFeedbackItem ? false : true>;
type _GeneratedHasRunIdSnake = _Assert<'run_id' extends keyof OpenApiItem ? true : false>;
type _GeneratedLacksRunIdCamel = _Assert<'runId' extends keyof OpenApiItem ? false : true>;

type _UiFeedbackRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'feedbackValue'> extends false ? true : false>;
type _UiNoteRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'note'> extends false ? true : false>;
type _UiSourceRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'source'> extends false ? true : false>;
type _UiProvenanceRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'provenanceSource'> extends false ? true : false>;
type _UiActorRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'actorId'> extends false ? true : false>;
type _UiCreatedRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'createdAt'> extends false ? true : false>;
type _UiUpdatedRequired = _Assert<IsOptional<AgentRunFeedbackItem, 'updatedAt'> extends false ? true : false>;
type _GeneratedFeedbackOptional = _Assert<IsOptional<OpenApiItem, 'feedback_value'>>;
type _NaiveCamelFeedbackOptional = _Assert<IsOptional<CamelizeKeys<OpenApiItem>, 'feedbackValue'>>;
type _UiFeedbackNullable = _Assert<null extends AgentRunFeedbackItem['feedbackValue'] ? true : false>;
type _OmitUiFeedback = _Assert<Omit<AgentRunFeedbackItem, 'feedbackValue'> extends AgentRunFeedbackItem ? false : true>;
type _OmitGeneratedFeedback = _Assert<Omit<OpenApiItem, 'feedback_value'> extends OpenApiItem ? true : false>;

type _ValueFromGenerated = _Assert<
  AgentRunFeedbackValue extends NonNullable<OpenApiItem['feedback_value']>
    ? NonNullable<OpenApiItem['feedback_value']> extends AgentRunFeedbackValue ? true : false
    : false
>;
type _StringValueRejected = _Assert<string extends AgentRunFeedbackValue ? false : true>;
type _OpenValueRejected = _Assert<'excellent' extends AgentRunFeedbackValue ? false : true>;
type _RequestNoteRequired = _Assert<IsOptional<AgentRunFeedbackRequest, 'note'> extends false ? true : false>;
type _RequestNoteIsString = _Assert<string extends AgentRunFeedbackRequest['note'] ? true : false>;
type _RequestNoteNotNull = _Assert<null extends AgentRunFeedbackRequest['note'] ? false : true>;
type _GeneratedNoteOptional = _Assert<IsOptional<OpenApiRequest, 'note'>>;
type _GeneratedNoteNullable = _Assert<null extends OpenApiRequest['note'] ? true : false>;
type _RequestSourceIsWeb = _Assert<AgentRunFeedbackRequest['source'] extends 'web' ? true : false>;
type _RequestSourceRejectsApi = _Assert<'api' extends AgentRunFeedbackRequest['source'] ? false : true>;
type _GeneratedSourceHasApi = _Assert<'api' extends OpenApiRequest['source'] ? true : false>;
type _NaiveDoesNotExtendPublic = _Assert<
  CamelizeKeys<OpenApiRequest> extends AgentRunFeedbackRequest ? false : true
>;

type ConsumerFixture = {
  runId: string;
  feedbackValue: 'useful';
  note: '';
  source: 'web';
  provenanceSource: 'user_feedback';
  actorId: null;
  createdAt: null;
  updatedAt: null;
};
type _ConsumerAssignable = _Assert<ConsumerFixture extends AgentRunFeedbackItem ? true : false>;
type MissingFeedback = Omit<ConsumerFixture, 'feedbackValue'>;
type _MissingFeedbackRejected = _Assert<MissingFeedback extends AgentRunFeedbackItem ? false : true>;
type EmptyNoteRequest = { feedbackValue: 'useful'; note: ''; source: 'web' };
type _EmptyNoteAccepted = _Assert<EmptyNoteRequest extends AgentRunFeedbackRequest ? true : false>;
type ApiSourceRequest = { feedbackValue: 'useful'; note: ''; source: 'api' };
type _ApiSourceRejected = _Assert<ApiSourceRequest extends AgentRunFeedbackRequest ? false : true>;
type NullNoteRequest = { feedbackValue: 'useful'; note: null; source: 'web' };
type _NullNoteRejected = _Assert<NullNoteRequest extends AgentRunFeedbackRequest ? false : true>;
type SnakeItem = { run_id: string };
type _SnakeMatchesGenerated = _Assert<SnakeItem extends OpenApiItem ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeItem extends AgentRunFeedbackItem ? false : true>;

type _CompileTimePins = [
  _TwoComponents, _Get200IsItem, _ItemIsGet200, _Put200IsItem, _ItemIsPut200,
  _PutBodyIsRequest, _RequestIsPutBody, _GetOpIsPath, _PathIsGetOp, _PutOpIsPath,
  _PathIsPutOp, _GetOpHasNeverRequestBody, _GetQueryNever, _PutQueryNever,
  _GetPathRunIdIsString, _PathPostNever, _PathDeleteNever, _PathPatchNever,
  _UiHasRunId, _UiHasFeedbackValue, _UiHasProvenanceSource, _UiLacksRunIdSnake,
  _UiLacksFeedbackValueSnake, _GeneratedHasRunIdSnake, _GeneratedLacksRunIdCamel,
  _UiFeedbackRequired, _UiNoteRequired, _UiSourceRequired, _UiProvenanceRequired,
  _UiActorRequired, _UiCreatedRequired, _UiUpdatedRequired, _GeneratedFeedbackOptional,
  _NaiveCamelFeedbackOptional, _UiFeedbackNullable, _OmitUiFeedback, _OmitGeneratedFeedback,
  _ValueFromGenerated, _StringValueRejected, _OpenValueRejected, _RequestNoteRequired,
  _RequestNoteIsString, _RequestNoteNotNull, _GeneratedNoteOptional, _GeneratedNoteNullable,
  _RequestSourceIsWeb, _RequestSourceRejectsApi, _GeneratedSourceHasApi,
  _NaiveDoesNotExtendPublic, _ConsumerAssignable, _MissingFeedbackRejected,
  _EmptyNoteAccepted, _ApiSourceRejected, _NullNoteRejected, _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
];

describe('agentFeedback OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...AgentFeedback }).toEqual({});
    expect(Object.keys(AgentFeedback)).toEqual([]);
    expect(Object.getOwnPropertyNames(AgentFeedback)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates GET/PUT 200 JSON to the generated item and PUT body to the generated request', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiPut200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiPutBody>().toEqualTypeOf<OpenApiRequest>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
    expectTypeOf<OpenApiPutOp>().toEqualTypeOf<OpenApiPathPut>();
    type HasNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    expectTypeOf<HasNeverBody>().toEqualTypeOf<true>();
  });

  it('keeps GET/PUT query never, path run_id string, and POST/DELETE/PATCH never', () => {
    type GetQueryNever = OpenApiGetOp['parameters']['query'] extends never | undefined ? true : false;
    type PutQueryNever = OpenApiPutOp['parameters']['query'] extends never | undefined ? true : false;
    expectTypeOf<GetQueryNever>().toEqualTypeOf<true>();
    expectTypeOf<PutQueryNever>().toEqualTypeOf<true>();
    expectTypeOf<OpenApiGetOp['parameters']['path']['run_id']>().toEqualTypeOf<string>();
    type PostNever = paths['/api/v1/agent/runs/{run_id}/feedback']['post'] extends never | undefined ? true : false;
    type DeleteNever = paths['/api/v1/agent/runs/{run_id}/feedback']['delete'] extends never | undefined ? true : false;
    type PatchNever = paths['/api/v1/agent/runs/{run_id}/feedback']['patch'] extends never | undefined ? true : false;
    expectTypeOf<PostNever>().toEqualTypeOf<true>();
    expectTypeOf<DeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<PatchNever>().toEqualTypeOf<true>();
  });

  it('keeps seven UI keys required-nullable versus generated and naive camel optionality', () => {
    expectTypeOf<Omit<AgentRunFeedbackItem, 'feedbackValue'>>().not.toMatchTypeOf<AgentRunFeedbackItem>();
    expectTypeOf<Omit<OpenApiItem, 'feedback_value'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<null>().toMatchTypeOf<AgentRunFeedbackItem['feedbackValue']>();
    expectTypeOf<null>().toMatchTypeOf<AgentRunFeedbackItem['note']>();
    expectTypeOf<AgentRunFeedbackValue>().toEqualTypeOf<'useful' | 'partial' | 'wrong' | 'harmful'>();
    expectTypeOf<string>().not.toMatchTypeOf<AgentRunFeedbackValue>();
    expectTypeOf<'excellent'>().not.toMatchTypeOf<AgentRunFeedbackValue>();
  });

  it('keeps the public request handwritten and narrower than generated CamelizeKeys', () => {
    expectTypeOf<AgentRunFeedbackRequest['note']>().toEqualTypeOf<string>();
    expectTypeOf<null>().not.toMatchTypeOf<AgentRunFeedbackRequest['note']>();
    expectTypeOf<AgentRunFeedbackRequest['source']>().toEqualTypeOf<'web'>();
    expectTypeOf<'api'>().not.toMatchTypeOf<AgentRunFeedbackRequest['source']>();
    expectTypeOf<CamelizeKeys<OpenApiRequest>>().not.toMatchTypeOf<AgentRunFeedbackRequest>();
    const emptyNote: AgentRunFeedbackRequest = { feedbackValue: 'useful', note: '', source: 'web' };
    expectTypeOf(emptyNote).toMatchTypeOf<AgentRunFeedbackRequest>();
  });

  it('keeps snake_case keys off the UI item and on the generated component', () => {
    expectTypeOf<keyof AgentRunFeedbackItem>().not.toMatchTypeOf<
      'run_id' | 'feedback_value' | 'provenance_source' | 'actor_id' | 'created_at' | 'updated_at'
    >();
    expectTypeOf<keyof OpenApiItem>().not.toMatchTypeOf<
      'runId' | 'feedbackValue' | 'provenanceSource' | 'actorId' | 'createdAt' | 'updatedAt'
    >();
    const snake = { run_id: 'run-a' };
    expectTypeOf(snake).toMatchTypeOf<OpenApiItem>();
    expectTypeOf(snake).not.toMatchTypeOf<AgentRunFeedbackItem>();
  });

  it('accepts one consumer-shaped fixture and rejects missing feedbackValue', () => {
    const fixture: AgentRunFeedbackItem = {
      runId: 'run-a',
      feedbackValue: 'useful',
      note: '',
      source: 'web',
      provenanceSource: 'user_feedback',
      actorId: null,
      createdAt: null,
      updatedAt: null,
    };
    expectTypeOf(fixture).toMatchTypeOf<AgentRunFeedbackItem>();
    expectTypeOf(fixture.feedbackValue).toMatchTypeOf<AgentRunFeedbackValue | null>();
  });
});
