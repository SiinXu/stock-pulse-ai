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

type _Assert<T extends true> = T;
type _Task200IsSnapshot = _Assert<OpenApiTaskFlowGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotIsTask200 = _Assert<OpenApiSnapshot extends OpenApiTaskFlowGet200 ? true : false>;
type _History200IsSnapshot = _Assert<OpenApiHistoryFlowGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotIsHistory200 = _Assert<OpenApiSnapshot extends OpenApiHistoryFlowGet200 ? true : false>;
type _TaskOpHasNeverRequestBody = _Assert<OpenApiTaskFlowOp extends { requestBody?: never } ? true : false>;
type _HistoryOpHasNeverRequestBody = _Assert<OpenApiHistoryFlowOp extends { requestBody?: never } ? true : false>;

type _OpenApiAnchors = [
  _Task200IsSnapshot,
  _SnapshotIsTask200,
  _History200IsSnapshot,
  _SnapshotIsHistory200,
  _TaskOpHasNeverRequestBody,
  _HistoryOpHasNeverRequestBody,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type RunFlowStatus = OpenApiSnapshot['status'];
export type RunFlowNodeKind = OpenApiNode['kind'];
export type RunFlowEdgeKind = OpenApiEdge['kind'];
export type RunFlowEventSeverity = OpenApiEvent['severity'];

export type RunFlowLane = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiLane>, {
  id: string;
  label: string;
  order: number;
}>>;

export type RunFlowNode = Override<CamelizeKeys<OpenApiNode>, {
  id: string;
  lane: string;
  kind: RunFlowNodeKind;
  label: string;
  status: RunFlowStatus;
  provider?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
  durationMs?: number | null;
  attempts?: number | null;
  recordCount?: number | null;
  message?: string | null;
  metadata?: Record<string, unknown>;
}>;

export type RunFlowEdge = Override<CamelizeKeys<OpenApiEdge>, {
  id: string;
  from: string;
  to: string;
  kind: RunFlowEdgeKind;
  status: RunFlowStatus;
  label?: string | null;
  message?: string | null;
  metadata?: Record<string, unknown>;
}>;

export type RunFlowEvent = Override<CamelizeKeys<OpenApiEvent>, {
  id: string;
  timestamp?: string | null;
  severity: RunFlowEventSeverity;
  type: string;
  nodeId?: string | null;
  title: string;
  message?: string | null;
  metadata?: Record<string, unknown>;
}>;

export type RunFlowSummary = Override<CamelizeKeys<OpenApiSummary>, {
  elapsedMs?: number | null;
  bottleneckNodeId?: string | null;
  failedAttempts: number;
  fallbackCount: number;
  model?: string | null;
  dataSourceCount: number;
  eventCount: number;
}>;

export type RunFlowSnapshot = Omit<Override<CamelizeKeys<OpenApiSnapshot>, {
  taskId: string;
  traceId?: string | null;
  stockCode: string;
  stockName?: string | null;
  status: RunFlowStatus;
  summary: RunFlowSummary;
  lanes: RunFlowLane[];
  nodes: RunFlowNode[];
  edges: RunFlowEdge[];
  events: RunFlowEvent[];
  generatedAt: string;
}>, 'schemaVersion'>;

export type RunFlowSnapshotSource =
  | { type: 'task'; taskId: string }
  | { type: 'history'; recordId: number };
