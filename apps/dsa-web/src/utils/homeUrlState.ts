// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { RunFlowSnapshotSource } from '../types/runFlow';
import { buildDeepLink, parseDeepLink, type HomeWorkspaceView } from './deepLink';

const HOME_RECORD_ID_PARAM = 'recordId';
const HOME_WORKSPACE_PARAM = 'workspace';
const HOME_RUN_FLOW_PARAM = 'runFlow';
const HOME_RUN_FLOW_RECORD_ID_PARAM = 'runFlowRecordId';
const HOME_RUN_FLOW_TASK_ID_PARAM = 'runFlowTaskId';
const STABLE_TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export type HomeUrlState = {
  recordId: number | null;
  runFlow: RunFlowSnapshotSource | null;
  stockCode: string | null;
  workspace: HomeWorkspaceView;
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

function parsePositiveInteger(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
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
  const recordId = parsePositiveInteger(params.get(HOME_RECORD_ID_PARAM));
  if (recordId === null) {
    normalized.delete(HOME_RECORD_ID_PARAM);
  } else {
    normalized.set(HOME_RECORD_ID_PARAM, String(recordId));
  }

  let runFlow: RunFlowSnapshotSource | null = null;
  const runFlowType = params.get(HOME_RUN_FLOW_PARAM);
  if (runFlowType === 'history') {
    const runFlowRecordId = parsePositiveInteger(params.get(HOME_RUN_FLOW_RECORD_ID_PARAM));
    if (runFlowRecordId !== null) {
      runFlow = { type: 'history', recordId: runFlowRecordId };
      normalized.set(HOME_RUN_FLOW_PARAM, 'history');
      normalized.set(HOME_RUN_FLOW_RECORD_ID_PARAM, String(runFlowRecordId));
      normalized.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
    }
  } else if (runFlowType === 'task') {
    const taskId = parseStableTaskId(params.get(HOME_RUN_FLOW_TASK_ID_PARAM));
    if (taskId !== null) {
      runFlow = { type: 'task', taskId };
      normalized.set(HOME_RUN_FLOW_PARAM, 'task');
      normalized.set(HOME_RUN_FLOW_TASK_ID_PARAM, taskId);
      normalized.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
    }
  }

  if (runFlow === null) {
    normalized.delete(HOME_RUN_FLOW_PARAM);
    normalized.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
    normalized.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
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
    workspace: homeTarget?.workspace ?? 'history',
    invalidRecordId: parsedDeepLink.issues.some((issue) => issue.code === 'invalid_record_id'),
    invalidRunFlow: (
      deepLinkParams.has(HOME_RUN_FLOW_PARAM)
      || deepLinkParams.has(HOME_RUN_FLOW_RECORD_ID_PARAM)
      || deepLinkParams.has(HOME_RUN_FLOW_TASK_ID_PARAM)
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
  params.set(HOME_RECORD_ID_PARAM, String(recordId));
  return toSearch(params);
}

export function clearHomeRecord(search: string): string {
  const params = getNormalizedParams(search);
  params.delete(HOME_RECORD_ID_PARAM);
  return toSearch(params);
}

export function setHomeTaskRunFlow(search: string, taskId: string): string {
  const parsedTaskId = parseStableTaskId(taskId);
  if (parsedTaskId === null) {
    return clearHomeRunFlow(search);
  }
  const params = getNormalizedParams(search);
  params.delete(HOME_RUN_FLOW_PARAM);
  params.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
  params.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
  params.set(HOME_RUN_FLOW_PARAM, 'task');
  params.set(HOME_RUN_FLOW_TASK_ID_PARAM, parsedTaskId);
  return toSearch(params);
}

export function setHomeHistoryRunFlow(search: string, recordId: number): string {
  const params = getNormalizedParams(search);
  params.delete(HOME_RUN_FLOW_PARAM);
  params.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
  params.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
  params.set(HOME_RUN_FLOW_PARAM, 'history');
  params.set(HOME_RUN_FLOW_RECORD_ID_PARAM, String(recordId));
  return toSearch(params);
}

export function buildHomeHistoryRunFlowHref(recordId: number, stockCode?: string): string {
  const baseHref = buildDeepLink({ page: 'home', recordId, stockCode });
  const baseUrl = new URL(baseHref, 'http://stockpulse.local');
  return `${baseUrl.pathname}${setHomeHistoryRunFlow(baseUrl.search, recordId)}`;
}

export function clearHomeRunFlow(search: string): string {
  const params = getNormalizedParams(search);
  params.delete(HOME_RUN_FLOW_PARAM);
  params.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
  params.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
  return toSearch(params);
}

export function setHomeWorkspace(search: string, workspace: HomeWorkspaceView): string {
  const params = getNormalizedParams(search);
  if (workspace === 'history') {
    params.delete(HOME_WORKSPACE_PARAM);
  } else {
    params.set(HOME_WORKSPACE_PARAM, workspace);
  }
  return toSearch(params);
}
