import type { RunFlowSnapshotSource } from '../types/runFlow';

const HOME_RECORD_ID_PARAM = 'recordId';
const HOME_RUN_FLOW_PARAM = 'runFlow';
const HOME_RUN_FLOW_RECORD_ID_PARAM = 'runFlowRecordId';
const HOME_RUN_FLOW_TASK_ID_PARAM = 'runFlowTaskId';
const STABLE_TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export type HomeUrlState = {
  recordId: number | null;
  runFlow: RunFlowSnapshotSource | null;
  invalidRecordId: boolean;
  invalidRunFlow: boolean;
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
  const rawParams = toSearchParams(search);
  const normalized = normalizeCoreParams(rawParams);
  const normalizedSearch = toSearch(normalized.params);
  return {
    recordId: normalized.recordId,
    runFlow: normalized.runFlow,
    invalidRecordId: rawParams.has(HOME_RECORD_ID_PARAM) && normalized.recordId === null,
    invalidRunFlow: (
      rawParams.has(HOME_RUN_FLOW_PARAM)
      || rawParams.has(HOME_RUN_FLOW_RECORD_ID_PARAM)
      || rawParams.has(HOME_RUN_FLOW_TASK_ID_PARAM)
    ) && normalized.runFlow === null,
    normalizedSearch,
    needsNormalization: normalizedSearch !== rawSearch,
  };
}

function getNormalizedParams(search: string): URLSearchParams {
  return normalizeCoreParams(toSearchParams(search)).params;
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

export function clearHomeRunFlow(search: string): string {
  const params = getNormalizedParams(search);
  params.delete(HOME_RUN_FLOW_PARAM);
  params.delete(HOME_RUN_FLOW_RECORD_ID_PARAM);
  params.delete(HOME_RUN_FLOW_TASK_ID_PARAM);
  return toSearch(params);
}
