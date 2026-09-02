// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as RunFlow from '../runFlow';
import type {
  RunFlowEdge,
  RunFlowEdgeKind,
  RunFlowEvent,
  RunFlowEventSeverity,
  RunFlowLane,
  RunFlowNode,
  RunFlowNodeKind,
  RunFlowSnapshot,
  RunFlowSnapshotSource,
  RunFlowStatus,
  RunFlowSummary,
} from '../runFlow';

type OpenApiLane = components['schemas']['RunFlowLane'];
type OpenApiNode = components['schemas']['RunFlowNode'];
type OpenApiEdge = components['schemas']['RunFlowEdge'];
type OpenApiEvent = components['schemas']['RunFlowEvent'];
type OpenApiSummary = components['schemas']['RunFlowSummary'];
type OpenApiSnapshot = components['schemas']['RunFlowSnapshot'];
type OpenApiTaskFlowGet200 =
  operations['get_task_run_flow_api_v1_analysis_tasks__task_id__flow_get']['responses']['200']['content']['application/json'];
type OpenApiHistoryFlowGet200 =
  operations['get_history_run_flow_api_v1_history__record_id__flow_get']['responses']['200']['content']['application/json'];
type OpenApiTaskFlowOp =
  operations['get_task_run_flow_api_v1_analysis_tasks__task_id__flow_get'];
type OpenApiHistoryFlowOp =
  operations['get_history_run_flow_api_v1_history__record_id__flow_get'];

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

type _Task200IsSnapshot = _Assert<OpenApiTaskFlowGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotIsTask200 = _Assert<OpenApiSnapshot extends OpenApiTaskFlowGet200 ? true : false>;
type _History200IsSnapshot = _Assert<OpenApiHistoryFlowGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotIsHistory200 = _Assert<OpenApiSnapshot extends OpenApiHistoryFlowGet200 ? true : false>;
type _TaskOpHasNeverRequestBody = _Assert<OpenApiTaskFlowOp extends { requestBody?: never } ? true : false>;
type _HistoryOpHasNeverRequestBody = _Assert<OpenApiHistoryFlowOp extends { requestBody?: never } ? true : false>;

type _UiHasTaskId = _Assert<'taskId' extends keyof RunFlowSnapshot ? true : false>;
type _UiHasStockCode = _Assert<'stockCode' extends keyof RunFlowSnapshot ? true : false>;
type _UiHasStockName = _Assert<'stockName' extends keyof RunFlowSnapshot ? true : false>;
type _UiHasTraceId = _Assert<'traceId' extends keyof RunFlowSnapshot ? true : false>;
type _UiHasGeneratedAt = _Assert<'generatedAt' extends keyof RunFlowSnapshot ? true : false>;
type _UiHasNodeId = _Assert<'nodeId' extends keyof RunFlowEvent ? true : false>;
type _UiHasStartedAt = _Assert<'startedAt' extends keyof RunFlowNode ? true : false>;
type _UiHasEndedAt = _Assert<'endedAt' extends keyof RunFlowNode ? true : false>;
type _UiHasDurationMs = _Assert<'durationMs' extends keyof RunFlowNode ? true : false>;
type _UiHasRecordCount = _Assert<'recordCount' extends keyof RunFlowNode ? true : false>;
type _UiHasFailedAttempts = _Assert<'failedAttempts' extends keyof RunFlowSummary ? true : false>;
type _UiHasFallbackCount = _Assert<'fallbackCount' extends keyof RunFlowSummary ? true : false>;
type _UiHasDataSourceCount = _Assert<'dataSourceCount' extends keyof RunFlowSummary ? true : false>;
type _UiHasEventCount = _Assert<'eventCount' extends keyof RunFlowSummary ? true : false>;
type _UiHasElapsedMs = _Assert<'elapsedMs' extends keyof RunFlowSummary ? true : false>;
type _UiHasBottleneckNodeId = _Assert<'bottleneckNodeId' extends keyof RunFlowSummary ? true : false>;
type _UiHasFrom = _Assert<'from' extends keyof RunFlowEdge ? true : false>;
type _UiHasTo = _Assert<'to' extends keyof RunFlowEdge ? true : false>;

type _UiLacksTaskIdSnake = _Assert<'task_id' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksStockNameSnake = _Assert<'stock_name' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksTraceIdSnake = _Assert<'trace_id' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksGeneratedAtSnake = _Assert<'generated_at' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksSchemaVersion = _Assert<'schemaVersion' extends keyof RunFlowSnapshot ? false : true>;
type _UiLacksNodeIdSnake = _Assert<'node_id' extends keyof RunFlowEvent ? false : true>;
type _UiLacksStartedAtSnake = _Assert<'started_at' extends keyof RunFlowNode ? false : true>;
type _UiLacksEndedAtSnake = _Assert<'ended_at' extends keyof RunFlowNode ? false : true>;
type _UiLacksDurationMsSnake = _Assert<'duration_ms' extends keyof RunFlowNode ? false : true>;
type _UiLacksRecordCountSnake = _Assert<'record_count' extends keyof RunFlowNode ? false : true>;
type _UiLacksFailedAttemptsSnake = _Assert<'failed_attempts' extends keyof RunFlowSummary ? false : true>;
type _UiLacksFallbackCountSnake = _Assert<'fallback_count' extends keyof RunFlowSummary ? false : true>;
type _UiLacksDataSourceCountSnake = _Assert<'data_source_count' extends keyof RunFlowSummary ? false : true>;
type _UiLacksEventCountSnake = _Assert<'event_count' extends keyof RunFlowSummary ? false : true>;
type _UiLacksElapsedMsSnake = _Assert<'elapsed_ms' extends keyof RunFlowSummary ? false : true>;
type _UiLacksBottleneckSnake = _Assert<'bottleneck_node_id' extends keyof RunFlowSummary ? false : true>;
type _UiLacksFromNode = _Assert<'fromNode' extends keyof RunFlowEdge ? false : true>;
type _UiLacksToNode = _Assert<'toNode' extends keyof RunFlowEdge ? false : true>;
type _UiLacksFromNodeSnake = _Assert<'from_node' extends keyof RunFlowEdge ? false : true>;
type _UiLacksToNodeSnake = _Assert<'to_node' extends keyof RunFlowEdge ? false : true>;

type _GeneratedHasTaskIdSnake = _Assert<'task_id' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasStockNameSnake = _Assert<'stock_name' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasTraceIdSnake = _Assert<'trace_id' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasGeneratedAtSnake = _Assert<'generated_at' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasNodeIdSnake = _Assert<'node_id' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasStartedAtSnake = _Assert<'started_at' extends keyof OpenApiNode ? true : false>;
type _GeneratedHasEndedAtSnake = _Assert<'ended_at' extends keyof OpenApiNode ? true : false>;
type _GeneratedHasDurationMsSnake = _Assert<'duration_ms' extends keyof OpenApiNode ? true : false>;
type _GeneratedHasRecordCountSnake = _Assert<'record_count' extends keyof OpenApiNode ? true : false>;
type _GeneratedHasFailedAttemptsSnake = _Assert<'failed_attempts' extends keyof OpenApiSummary ? true : false>;
type _GeneratedHasFallbackCountSnake = _Assert<'fallback_count' extends keyof OpenApiSummary ? true : false>;
type _GeneratedHasDataSourceCountSnake = _Assert<'data_source_count' extends keyof OpenApiSummary ? true : false>;
type _GeneratedHasEventCountSnake = _Assert<'event_count' extends keyof OpenApiSummary ? true : false>;
type _GeneratedHasElapsedMsSnake = _Assert<'elapsed_ms' extends keyof OpenApiSummary ? true : false>;
type _GeneratedHasBottleneckSnake = _Assert<'bottleneck_node_id' extends keyof OpenApiSummary ? true : false>;
type _GeneratedLaneHasId = _Assert<'id' extends keyof OpenApiLane ? true : false>;
type _GeneratedHasFrom = _Assert<'from' extends keyof OpenApiEdge ? true : false>;
type _GeneratedHasTo = _Assert<'to' extends keyof OpenApiEdge ? true : false>;
type _GeneratedLacksFromNodeSnake = _Assert<'from_node' extends keyof OpenApiEdge ? false : true>;
type _GeneratedLacksToNodeSnake = _Assert<'to_node' extends keyof OpenApiEdge ? false : true>;
type _GeneratedLacksTaskIdCamel = _Assert<'taskId' extends keyof OpenApiSnapshot ? false : true>;
type _GeneratedLacksSchemaVersionCamel = _Assert<'schemaVersion' extends keyof OpenApiSnapshot ? false : true>;

type _NaiveCamelHasSchemaVersion = _Assert<'schemaVersion' extends keyof CamelizeKeys<OpenApiSnapshot> ? true : false>;
type _NaiveCamelLanesOptional = _Assert<IsOptional<CamelizeKeys<OpenApiSnapshot>, 'lanes'>>;
type _UiLanesRequired = _Assert<IsOptional<RunFlowSnapshot, 'lanes'> extends false ? true : false>;
type _UiNodesRequired = _Assert<IsOptional<RunFlowSnapshot, 'nodes'> extends false ? true : false>;
type _UiEdgesRequired = _Assert<IsOptional<RunFlowSnapshot, 'edges'> extends false ? true : false>;
type _UiEventsRequired = _Assert<IsOptional<RunFlowSnapshot, 'events'> extends false ? true : false>;
type _GeneratedLanesOptional = _Assert<IsOptional<OpenApiSnapshot, 'lanes'>>;
type _GeneratedNodesOptional = _Assert<IsOptional<OpenApiSnapshot, 'nodes'>>;
type _GeneratedEdgesOptional = _Assert<IsOptional<OpenApiSnapshot, 'edges'>>;
type _GeneratedEventsOptional = _Assert<IsOptional<OpenApiSnapshot, 'events'>>;

type _FailedAttemptsRequired = _Assert<IsOptional<RunFlowSummary, 'failedAttempts'> extends false ? true : false>;
type _FallbackCountRequired = _Assert<IsOptional<RunFlowSummary, 'fallbackCount'> extends false ? true : false>;
type _DataSourceCountRequired = _Assert<IsOptional<RunFlowSummary, 'dataSourceCount'> extends false ? true : false>;
type _EventCountRequired = _Assert<IsOptional<RunFlowSummary, 'eventCount'> extends false ? true : false>;
type _GeneratedFailedAttemptsRequired = _Assert<
  IsOptional<OpenApiSummary, 'failed_attempts'> extends false ? true : false
>;
type _GeneratedFallbackCountRequired = _Assert<
  IsOptional<OpenApiSummary, 'fallback_count'> extends false ? true : false
>;

type _OmitUiLanes = _Assert<Omit<RunFlowSnapshot, 'lanes'> extends RunFlowSnapshot ? false : true>;
type _OmitUiNodes = _Assert<Omit<RunFlowSnapshot, 'nodes'> extends RunFlowSnapshot ? false : true>;
type _OmitUiEdges = _Assert<Omit<RunFlowSnapshot, 'edges'> extends RunFlowSnapshot ? false : true>;
type _OmitUiEvents = _Assert<Omit<RunFlowSnapshot, 'events'> extends RunFlowSnapshot ? false : true>;
type _OmitUiArrays = _Assert<
  Omit<RunFlowSnapshot, 'lanes' | 'nodes' | 'edges' | 'events'> extends RunFlowSnapshot ? false : true
>;
type _OmitGeneratedLanes = _Assert<Omit<OpenApiSnapshot, 'lanes'> extends OpenApiSnapshot ? true : false>;
type _OmitGeneratedNodes = _Assert<Omit<OpenApiSnapshot, 'nodes'> extends OpenApiSnapshot ? true : false>;
type _OmitGeneratedEdges = _Assert<Omit<OpenApiSnapshot, 'edges'> extends OpenApiSnapshot ? true : false>;
type _OmitGeneratedEvents = _Assert<Omit<OpenApiSnapshot, 'events'> extends OpenApiSnapshot ? true : false>;
type _OmitGeneratedArrays = _Assert<
  Omit<OpenApiSnapshot, 'lanes' | 'nodes' | 'edges' | 'events'> extends OpenApiSnapshot ? true : false
>;
type _OmitGeneratedSchemaVersion = _Assert<
  Omit<OpenApiSnapshot, 'schema_version'> extends OpenApiSnapshot ? false : true
>;
type _OmitFailedAttempts = _Assert<Omit<RunFlowSummary, 'failedAttempts'> extends RunFlowSummary ? false : true>;
type _OmitFallbackCount = _Assert<Omit<RunFlowSummary, 'fallbackCount'> extends RunFlowSummary ? false : true>;
type _OmitDataSourceCount = _Assert<Omit<RunFlowSummary, 'dataSourceCount'> extends RunFlowSummary ? false : true>;
type _OmitEventCount = _Assert<Omit<RunFlowSummary, 'eventCount'> extends RunFlowSummary ? false : true>;

type _EntryKindAssignable = _Assert<'entry' extends RunFlowNodeKind ? true : false>;
type _OtherKindRejected = _Assert<'other' extends RunFlowNodeKind ? false : true>;
type _StringKindRejected = _Assert<string extends RunFlowNodeKind ? false : true>;
type _RetryEdgeAssignable = _Assert<'retry' extends RunFlowEdgeKind ? true : false>;
type _MaybeEdgeRejected = _Assert<'maybe' extends RunFlowEdgeKind ? false : true>;
type _StringEdgeRejected = _Assert<string extends RunFlowEdgeKind ? false : true>;
type _DangerSeverityAssignable = _Assert<'danger' extends RunFlowEventSeverity ? true : false>;
type _FatalSeverityRejected = _Assert<'fatal' extends RunFlowEventSeverity ? false : true>;
type _StringSeverityRejected = _Assert<string extends RunFlowEventSeverity ? false : true>;
type _DegradedStatusAssignable = _Assert<'degraded' extends RunFlowStatus ? true : false>;
type _MysteryStatusRejected = _Assert<'mystery' extends RunFlowStatus ? false : true>;
type _StringStatusRejected = _Assert<string extends RunFlowStatus ? false : true>;
type _NodeStatusIsSnapshotStatus = _Assert<OpenApiNode['status'] extends OpenApiSnapshot['status'] ? true : false>;
type _SnapshotStatusIsNodeStatus = _Assert<OpenApiSnapshot['status'] extends OpenApiNode['status'] ? true : false>;
type _EdgeStatusIsSnapshotStatus = _Assert<OpenApiEdge['status'] extends OpenApiSnapshot['status'] ? true : false>;

type NarrowLane = { id: string; label: string; order: number };
type NarrowSummary = {
  failedAttempts: number;
  fallbackCount: number;
  dataSourceCount: number;
  eventCount: number;
};
type NarrowSnapshot = {
  taskId: string;
  stockCode: string;
  status: 'success';
  summary: NarrowSummary;
  lanes: NarrowLane[];
  nodes: [];
  edges: [];
  events: [];
  generatedAt: string;
};
type _NarrowSnapshotAssignable = _Assert<NarrowSnapshot extends RunFlowSnapshot ? true : false>;
type _TaskSourceAssignable = _Assert<{ type: 'task'; taskId: string } extends RunFlowSnapshotSource ? true : false>;
type _HistorySourceAssignable = _Assert<
  { type: 'history'; recordId: number } extends RunFlowSnapshotSource ? true : false
>;
type _OtherSourceRejected = _Assert<{ type: 'other'; taskId: string } extends RunFlowSnapshotSource ? false : true>;
type _HistoryStringIdRejected = _Assert<
  { type: 'history'; recordId: string } extends RunFlowSnapshotSource ? false : true
>;
type _SnakeSourceRejected = _Assert<{ type: 'task'; task_id: string } extends RunFlowSnapshotSource ? false : true>;

type SnakeSnapshot = {
  task_id: string;
  stock_code: string;
  status: 'success';
  summary: {
    failed_attempts: number;
    fallback_count: number;
    data_source_count: number;
    event_count: number;
  };
  generated_at: string;
  schema_version: string;
};
type _SnakeMatchesGenerated = _Assert<SnakeSnapshot extends OpenApiSnapshot ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeSnapshot extends RunFlowSnapshot ? false : true>;

type _CompileTimePins = [
  _Task200IsSnapshot,
  _SnapshotIsTask200,
  _History200IsSnapshot,
  _SnapshotIsHistory200,
  _TaskOpHasNeverRequestBody,
  _HistoryOpHasNeverRequestBody,
  _UiHasTaskId,
  _UiHasStockCode,
  _UiHasStockName,
  _UiHasTraceId,
  _UiHasGeneratedAt,
  _UiHasNodeId,
  _UiHasStartedAt,
  _UiHasEndedAt,
  _UiHasDurationMs,
  _UiHasRecordCount,
  _UiHasFailedAttempts,
  _UiHasFallbackCount,
  _UiHasDataSourceCount,
  _UiHasEventCount,
  _UiHasElapsedMs,
  _UiHasBottleneckNodeId,
  _UiHasFrom,
  _UiHasTo,
  _UiLacksTaskIdSnake,
  _UiLacksStockCodeSnake,
  _UiLacksStockNameSnake,
  _UiLacksTraceIdSnake,
  _UiLacksGeneratedAtSnake,
  _UiLacksSchemaVersionSnake,
  _UiLacksSchemaVersion,
  _UiLacksNodeIdSnake,
  _UiLacksStartedAtSnake,
  _UiLacksEndedAtSnake,
  _UiLacksDurationMsSnake,
  _UiLacksRecordCountSnake,
  _UiLacksFailedAttemptsSnake,
  _UiLacksFallbackCountSnake,
  _UiLacksDataSourceCountSnake,
  _UiLacksEventCountSnake,
  _UiLacksElapsedMsSnake,
  _UiLacksBottleneckSnake,
  _UiLacksFromNode,
  _UiLacksToNode,
  _UiLacksFromNodeSnake,
  _UiLacksToNodeSnake,
  _GeneratedHasTaskIdSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasStockNameSnake,
  _GeneratedHasTraceIdSnake,
  _GeneratedHasGeneratedAtSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasNodeIdSnake,
  _GeneratedHasStartedAtSnake,
  _GeneratedHasEndedAtSnake,
  _GeneratedHasDurationMsSnake,
  _GeneratedHasRecordCountSnake,
  _GeneratedHasFailedAttemptsSnake,
  _GeneratedHasFallbackCountSnake,
  _GeneratedHasDataSourceCountSnake,
  _GeneratedHasEventCountSnake,
  _GeneratedHasElapsedMsSnake,
  _GeneratedHasBottleneckSnake,
  _GeneratedLaneHasId,
  _GeneratedHasFrom,
  _GeneratedHasTo,
  _GeneratedLacksFromNodeSnake,
  _GeneratedLacksToNodeSnake,
  _GeneratedLacksTaskIdCamel,
  _GeneratedLacksSchemaVersionCamel,
  _NaiveCamelHasSchemaVersion,
  _NaiveCamelLanesOptional,
  _UiLanesRequired,
  _UiNodesRequired,
  _UiEdgesRequired,
  _UiEventsRequired,
  _GeneratedLanesOptional,
  _GeneratedNodesOptional,
  _GeneratedEdgesOptional,
  _GeneratedEventsOptional,
  _FailedAttemptsRequired,
  _FallbackCountRequired,
  _DataSourceCountRequired,
  _EventCountRequired,
  _GeneratedFailedAttemptsRequired,
  _GeneratedFallbackCountRequired,
  _OmitUiLanes,
  _OmitUiNodes,
  _OmitUiEdges,
  _OmitUiEvents,
  _OmitUiArrays,
  _OmitGeneratedLanes,
  _OmitGeneratedNodes,
  _OmitGeneratedEdges,
  _OmitGeneratedEvents,
  _OmitGeneratedArrays,
  _OmitGeneratedSchemaVersion,
  _OmitFailedAttempts,
  _OmitFallbackCount,
  _OmitDataSourceCount,
  _OmitEventCount,
  _EntryKindAssignable,
  _OtherKindRejected,
  _StringKindRejected,
  _RetryEdgeAssignable,
  _MaybeEdgeRejected,
  _StringEdgeRejected,
  _DangerSeverityAssignable,
  _FatalSeverityRejected,
  _StringSeverityRejected,
  _DegradedStatusAssignable,
  _MysteryStatusRejected,
  _StringStatusRejected,
  _NodeStatusIsSnapshotStatus,
  _SnapshotStatusIsNodeStatus,
  _EdgeStatusIsSnapshotStatus,
  _NarrowSnapshotAssignable,
  _TaskSourceAssignable,
  _HistorySourceAssignable,
  _OtherSourceRejected,
  _HistoryStringIdRejected,
  _SnakeSourceRejected,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
];

const NODE_REST = {
  id: 'n1',
  lane: 'data',
  label: 'Node',
  status: 'success' as const,
};

const EDGE_REST = {
  id: 'e1',
  from: 'a',
  to: 'b',
  status: 'success' as const,
};

const EVENT_REST = {
  id: 'ev1',
  type: 'task_started',
  title: 'Started',
};

const STATUS_REST = {
  taskId: 'task-1',
  stockCode: '600519',
  summary: {
    failedAttempts: 0,
    fallbackCount: 0,
    dataSourceCount: 0,
    eventCount: 0,
  },
  lanes: [] as RunFlowLane[],
  nodes: [] as RunFlowNode[],
  edges: [] as RunFlowEdge[],
  events: [] as RunFlowEvent[],
  generatedAt: '2026-09-03T00:00:00Z',
};

describe('runFlow OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...RunFlow }).toEqual({});
    expect(Object.keys(RunFlow)).toEqual([]);
    expect(Object.getOwnPropertyNames(RunFlow)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates both path 200 JSON bodies to the generated snapshot component', () => {
    expectTypeOf<OpenApiTaskFlowGet200>().toEqualTypeOf<OpenApiSnapshot>();
    expectTypeOf<OpenApiHistoryFlowGet200>().toEqualTypeOf<OpenApiSnapshot>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof RunFlowSnapshot>().not.toMatchTypeOf<
      'task_id' | 'stock_code' | 'stock_name' | 'trace_id' | 'generated_at' | 'schema_version'
    >();
    expectTypeOf<keyof RunFlowNode>().not.toMatchTypeOf<
      'started_at' | 'ended_at' | 'duration_ms' | 'record_count'
    >();
    expectTypeOf<keyof RunFlowEvent>().not.toMatchTypeOf<'node_id'>();
    expectTypeOf<keyof RunFlowSummary>().not.toMatchTypeOf<
      'failed_attempts' | 'fallback_count' | 'data_source_count' | 'event_count' | 'elapsed_ms' | 'bottleneck_node_id'
    >();

    type UiHasTaskId = 'taskId' extends keyof RunFlowSnapshot ? true : false;
    type UiHasTaskIdSnake = 'task_id' extends keyof RunFlowSnapshot ? true : false;
    type GeneratedHasTaskIdSnake = 'task_id' extends keyof OpenApiSnapshot ? true : false;
    type UiHasSchemaVersion = 'schemaVersion' extends keyof RunFlowSnapshot ? true : false;
    type UiHasSchemaVersionSnake = 'schema_version' extends keyof RunFlowSnapshot ? true : false;
    type GeneratedHasSchemaVersionSnake = 'schema_version' extends keyof OpenApiSnapshot ? true : false;
    type UiHasFrom = 'from' extends keyof RunFlowEdge ? true : false;
    type UiHasFromNode = 'fromNode' extends keyof RunFlowEdge ? true : false;
    type GeneratedHasFrom = 'from' extends keyof OpenApiEdge ? true : false;
    type GeneratedHasFromNodeSnake = 'from_node' extends keyof OpenApiEdge ? true : false;

    expectTypeOf<UiHasTaskId>().toEqualTypeOf<true>();
    expectTypeOf<UiHasTaskIdSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasTaskIdSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSchemaVersion>().toEqualTypeOf<false>();
    expectTypeOf<UiHasSchemaVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSchemaVersionSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFrom>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFromNode>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasFrom>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasFromNodeSnake>().toEqualTypeOf<false>();
  });

  it('keeps UI snapshot arrays required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<RunFlowSnapshot, 'lanes' | 'nodes' | 'edges' | 'events'>>().not.toMatchTypeOf<RunFlowSnapshot>();
    expectTypeOf<Omit<OpenApiSnapshot, 'lanes' | 'nodes' | 'edges' | 'events'>>().toMatchTypeOf<OpenApiSnapshot>();
    expectTypeOf<Omit<RunFlowSnapshot, 'lanes'>>().not.toMatchTypeOf<RunFlowSnapshot>();
    expectTypeOf<Omit<OpenApiSnapshot, 'lanes'>>().toMatchTypeOf<OpenApiSnapshot>();
  });

  it('omits schemaVersion from the public UI snapshot while generated schema_version stays required', () => {
    type UiHasSchemaVersion = 'schemaVersion' extends keyof RunFlowSnapshot ? true : false;
    type UiHasSchemaVersionSnake = 'schema_version' extends keyof RunFlowSnapshot ? true : false;
    type GeneratedHasSchemaVersionSnake = 'schema_version' extends keyof OpenApiSnapshot ? true : false;
    expectTypeOf<UiHasSchemaVersion>().toEqualTypeOf<false>();
    expectTypeOf<UiHasSchemaVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSchemaVersionSnake>().toEqualTypeOf<true>();
    expectTypeOf<Omit<OpenApiSnapshot, 'schema_version'>>().not.toMatchTypeOf<OpenApiSnapshot>();
  });

  it('keeps summary counts required on the UI type', () => {
    expectTypeOf<Omit<RunFlowSummary, 'failedAttempts'>>().not.toMatchTypeOf<RunFlowSummary>();
    expectTypeOf<Omit<RunFlowSummary, 'fallbackCount'>>().not.toMatchTypeOf<RunFlowSummary>();
    expectTypeOf<Omit<RunFlowSummary, 'dataSourceCount'>>().not.toMatchTypeOf<RunFlowSummary>();
    expectTypeOf<Omit<RunFlowSummary, 'eventCount'>>().not.toMatchTypeOf<RunFlowSummary>();
  });

  it('rejects values outside the closed status, kind, and severity unions', () => {
    expectTypeOf({ kind: 'entry' as const, ...NODE_REST }).toMatchTypeOf<RunFlowNode>();
    expectTypeOf({ kind: 'other' as const, ...NODE_REST }).not.toMatchTypeOf<RunFlowNode>();
    expectTypeOf({ kind: 'entry' as string, ...NODE_REST }).not.toMatchTypeOf<RunFlowNode>();
    expectTypeOf({ kind: 'retry' as const, ...EDGE_REST }).toMatchTypeOf<RunFlowEdge>();
    expectTypeOf({ kind: 'maybe' as const, ...EDGE_REST }).not.toMatchTypeOf<RunFlowEdge>();
    expectTypeOf({ severity: 'danger' as const, ...EVENT_REST }).toMatchTypeOf<RunFlowEvent>();
    expectTypeOf({ severity: 'fatal' as const, ...EVENT_REST }).not.toMatchTypeOf<RunFlowEvent>();
    expectTypeOf({ status: 'degraded' as const, ...STATUS_REST }).toMatchTypeOf<RunFlowSnapshot>();
    expectTypeOf({ status: 'mystery' as const, ...STATUS_REST }).not.toMatchTypeOf<RunFlowSnapshot>();
  });

  it('still accepts a narrow playground-shaped snapshot and handwritten sources', () => {
    const snapshot = {
      taskId: 'fixture-task-101',
      stockCode: '600519',
      status: 'success' as const,
      summary: {
        failedAttempts: 0,
        fallbackCount: 0,
        dataSourceCount: 0,
        eventCount: 0,
      },
      lanes: [] as RunFlowLane[],
      nodes: [] as RunFlowNode[],
      edges: [] as RunFlowEdge[],
      events: [] as RunFlowEvent[],
      generatedAt: '2026-09-03T00:00:00Z',
    };
    expectTypeOf(snapshot).toMatchTypeOf<RunFlowSnapshot>();
    expectTypeOf({ type: 'task' as const, taskId: 'task-1' }).toMatchTypeOf<RunFlowSnapshotSource>();
    expectTypeOf({ type: 'history' as const, recordId: 12 }).toMatchTypeOf<RunFlowSnapshotSource>();
    expectTypeOf({ type: 'other' as const, taskId: 'task-1' }).not.toMatchTypeOf<RunFlowSnapshotSource>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeSnapshot = {
      task_id: 'task-1',
      stock_code: '600519',
      status: 'success' as const,
      summary: {
        failed_attempts: 0,
        fallback_count: 0,
        data_source_count: 0,
        event_count: 0,
      },
      generated_at: '2026-09-03T00:00:00Z',
      schema_version: 'run-flow-v1',
    };
    expectTypeOf(snakeSnapshot).toMatchTypeOf<OpenApiSnapshot>();
    expectTypeOf(snakeSnapshot).not.toMatchTypeOf<RunFlowSnapshot>();
  });
});
