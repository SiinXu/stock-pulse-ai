// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { RunFlowSnapshotSource } from '../types/runFlow';
import {
  HOME_ROUTE_QUERY_KEYS,
  HOME_WORKSPACE_VALUES,
  REPORT_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  parsePositiveRouteInteger,
  type HomeWorkspaceValue,
} from '../routing/routes';
import { buildDeepLink, parseDeepLink } from './deepLink';

const STABLE_TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export type HomeUrlState = {
  recordId: number | null;
  runFlow: RunFlowSnapshotSource | null;
  stockCode: string | null;
  workspace: HomeWorkspaceValue;
  invalidRecordId: boolean;
  invalidRunFlow: boolean;
  invalidStockCode: boolean;
  invalidWorkspace: boolean;
  sensitiveParameterRemoved: boolean;
  normalizedSearch: string;
  needsNormalization: boolean;
};

function toSearch(params: URLSearchParams): string {
  const value = params.toString();
  return value ? `?${value}` : '';
}

function toSearchParams(search: string): URLSearchParams {
  return new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
}

function parseStableTaskId(value: string | null): string | null {
  const parsed = value?.trim() ?? '';
  return STABLE_TASK_ID_PATTERN.test(parsed) ? parsed : null;
}

function normalizeCoreParams(params: URLSearchParams): {
  params: URLSearchParams;
  recordId: number | null;
  runFlow: RunFlowSnapshotSource | null;
} {
  const normalized = new URLSearchParams(params);
  const recordId = parsePositiveRouteInteger(params.get(REPORT_ROUTE_QUERY_KEYS.recordId));
  if (recordId === null) {
    normalized.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
  } else {
    normalized.set(REPORT_ROUTE_QUERY_KEYS.recordId, String(recordId));
  }

  let runFlow: RunFlowSnapshotSource | null = null;
  const runFlowType = params.get(REPORT_ROUTE_QUERY_KEYS.runFlow);
  if (runFlowType === RUN_FLOW_ROUTE_QUERY_VALUES.history) {
    const runFlowRecordId = parsePositiveRouteInteger(
      params.get(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId),
    );
    if (runFlowRecordId !== null) {
      runFlow = { type: 'history', recordId: runFlowRecordId };
      normalized.set(REPORT_ROUTE_QUERY_KEYS.runFlow, RUN_FLOW_ROUTE_QUERY_VALUES.history);
      normalized.set(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId, String(runFlowRecordId));
      normalized.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);
    }
  } else if (runFlowType === RUN_FLOW_ROUTE_QUERY_VALUES.task) {
    const taskId = parseStableTaskId(params.get(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId));
    if (taskId !== null) {
      runFlow = { type: 'task', taskId };
      normalized.set(REPORT_ROUTE_QUERY_KEYS.runFlow, RUN_FLOW_ROUTE_QUERY_VALUES.task);
      normalized.set(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId, taskId);
      normalized.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
    }
  }

  if (runFlow === null) {
    normalized.delete(REPORT_ROUTE_QUERY_KEYS.runFlow);
    normalized.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
    normalized.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);
  }

  return { params: normalized, recordId, runFlow };
}

export function parseHomeUrlState(search: string): HomeUrlState {
  const rawSearch = search && !search.startsWith('?') ? `?${search}` : search;
  const parsedDeepLink = parseDeepLink(`/${rawSearch}`);
  const deepLinkParams = toSearchParams(parsedDeepLink.normalizedSearch);
  const normalized = normalizeCoreParams(deepLinkParams);
  const normalizedSearch = toSearch(normalized.params);
  const homeTarget = parsedDeepLink.target?.page === 'home' ? parsedDeepLink.target : null;
  return {
    recordId: normalized.recordId,
    runFlow: normalized.runFlow,
    stockCode: homeTarget?.stockCode ?? null,
    workspace: homeTarget?.workspace ?? HOME_WORKSPACE_VALUES.history,
    invalidRecordId: parsedDeepLink.issues.some((issue) => issue.code === 'invalid_record_id'),
    invalidRunFlow: (
      deepLinkParams.has(REPORT_ROUTE_QUERY_KEYS.runFlow)
      || deepLinkParams.has(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId)
      || deepLinkParams.has(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId)
    ) && normalized.runFlow === null,
    invalidStockCode: parsedDeepLink.issues.some((issue) => issue.code === 'invalid_stock_code'),
    invalidWorkspace: parsedDeepLink.issues.some((issue) => issue.code === 'invalid_workspace'),
    sensitiveParameterRemoved: parsedDeepLink.issues.some((issue) => issue.code === 'sensitive_parameter'),
    normalizedSearch,
    needsNormalization: normalizedSearch !== rawSearch,
  };
}

function getNormalizedParams(search: string): URLSearchParams {
  return toSearchParams(parseHomeUrlState(search).normalizedSearch);
}

export function setHomeRecord(search: string, recordId: number): string {
  const params = getNormalizedParams(search);
  params.set(REPORT_ROUTE_QUERY_KEYS.recordId, String(recordId));
  return toSearch(params);
}

export function clearHomeRecord(search: string): string {
  const params = getNormalizedParams(search);
  params.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
  return toSearch(params);
}

export function setHomeTaskRunFlow(search: string, taskId: string): string {
  const parsedTaskId = parseStableTaskId(taskId);
  if (parsedTaskId === null) {
    return clearHomeRunFlow(search);
  }
  const params = getNormalizedParams(search);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlow);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);
  params.set(REPORT_ROUTE_QUERY_KEYS.runFlow, RUN_FLOW_ROUTE_QUERY_VALUES.task);
  params.set(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId, parsedTaskId);
  return toSearch(params);
}

export function setHomeHistoryRunFlow(search: string, recordId: number): string {
  const params = getNormalizedParams(search);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlow);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);
  params.set(REPORT_ROUTE_QUERY_KEYS.runFlow, RUN_FLOW_ROUTE_QUERY_VALUES.history);
  params.set(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId, String(recordId));
  return toSearch(params);
}

export function buildHomeHistoryRunFlowHref(recordId: number, stockCode?: string): string {
  const baseHref = buildDeepLink({ page: 'home', recordId, stockCode });
  const baseUrl = new URL(baseHref, 'http://stockpulse.local');
  return `${baseUrl.pathname}${setHomeHistoryRunFlow(baseUrl.search, recordId)}`;
}

export function clearHomeRunFlow(search: string): string {
  const params = getNormalizedParams(search);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlow);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
  params.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);
  return toSearch(params);
}

export function setHomeWorkspace(search: string, workspace: HomeWorkspaceValue): string {
  const params = getNormalizedParams(search);
  if (workspace === HOME_WORKSPACE_VALUES.history) {
    params.delete(HOME_ROUTE_QUERY_KEYS.workspace);
  } else {
    params.set(HOME_ROUTE_QUERY_KEYS.workspace, workspace);
  }
  return toSearch(params);
}
