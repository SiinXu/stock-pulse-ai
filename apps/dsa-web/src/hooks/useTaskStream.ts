import { useEffect, useRef, useCallback, useState, type MutableRefObject } from 'react';
import { analysisApi } from '../api/analysis';
import { toCamelCase } from '../api/utils';
import type { TaskInfo, TaskStatus } from '../types/analysis';
import type { RunFlowEvent } from '../types/runFlow';

/**
 * SSE event types.
 */
export type SSEEventType =
  | 'connected'
  | 'task_created'
  | 'task_started'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  | 'heartbeat';

/**
 * SSE event payload.
 */
export interface SSEEvent {
  type: SSEEventType;
  task?: TaskInfo;
  flowEvent?: RunFlowEvent;
  timestamp?: string;
}

/**
 * SSE hook options.
 */
export interface UseTaskStreamOptions {
  /** Task created callback */
  onTaskCreated?: (task: TaskInfo) => void;
  /** Task started callback */
  onTaskStarted?: (task: TaskInfo) => void;
  /** Task completed callback */
  onTaskCompleted?: (task: TaskInfo) => void;
  /** Task progress callback */
  onTaskProgress?: (task: TaskInfo) => void;
  /** Task failed callback */
  onTaskFailed?: (task: TaskInfo) => void;
  /** Incremental run-flow event callback carried by task_progress */
  onTaskFlowEvent?: (task: TaskInfo, event: RunFlowEvent) => void;
  /** Connected callback */
  onConnected?: () => void;
  /** Connection error callback */
  onError?: (error: Event) => void;
  /** Whether to reconnect automatically */
  autoReconnect?: boolean;
  /** Reconnect delay in milliseconds */
  reconnectDelay?: number;
  /** Whether the hook is enabled */
  enabled?: boolean;
  /** Tasks that must remain recoverable while SSE is unavailable. */
  trackedTasks?: readonly TaskInfo[];
  /** Delay between targeted status polls while SSE is unavailable. */
  pollingInterval?: number;
}

/**
 * SSE hook result.
 */
export interface UseTaskStreamResult {
  /** Whether the stream is connected */
  isConnected: boolean;
  /** Reconnect manually */
  reconnect: () => void;
  /** Disconnect manually */
  disconnect: () => void;
}

type TaskStreamCallbacks = Pick<
  UseTaskStreamOptions,
  | 'onTaskCreated'
  | 'onTaskStarted'
  | 'onTaskCompleted'
  | 'onTaskProgress'
  | 'onTaskFailed'
  | 'onTaskFlowEvent'
  | 'onConnected'
  | 'onError'
>;

type ParsedTaskStreamPayload = {
  task: TaskInfo;
  flowEvent?: RunFlowEvent;
};

type TaskStreamSubscriber = {
  callbacksRef: MutableRefObject<TaskStreamCallbacks>;
  setIsConnected: (value: boolean) => void;
  autoReconnect: boolean;
  reconnectDelay: number;
  trackedTasksRef: MutableRefObject<readonly TaskInfo[]>;
  pollingInterval: number;
};

let sharedEventSource: EventSource | null = null;
let sharedReconnectTimeout: ReturnType<typeof setTimeout> | null = null;
let sharedPollingTimeout: ReturnType<typeof setTimeout> | null = null;
let sharedPollInFlight = false;
let sharedConnected = false;
let nextSubscriberId = 1;
const subscribers = new Map<number, TaskStreamSubscriber>();
const lastDeliveredSignatures = new Map<string, string>();
const lastDeliveredRevisions = new Map<string, number>();

// Convert snake_case payloads into camelCase TaskInfo objects.
const toTaskInfo = (data: Record<string, unknown>): TaskInfo => {
  const task: TaskInfo = {
    taskId: data.task_id as string,
    stockCode: data.stock_code as string,
    stockName: data.stock_name as string | undefined,
    status: data.status as TaskInfo['status'],
    progress: data.progress as number,
    message: data.message as string | undefined,
    messageCode: data.message_code as string | undefined,
    messageParams: data.message_params && typeof data.message_params === 'object'
      ? data.message_params as Record<string, unknown>
      : undefined,
    reportType: data.report_type as string,
    createdAt: data.created_at as string,
    startedAt: data.started_at as string | undefined,
    completedAt: data.completed_at as string | undefined,
    error: data.error as string | undefined,
    errorCode: data.error_code as string | undefined,
    errorParams: data.error_params && typeof data.error_params === 'object'
      ? data.error_params as Record<string, unknown>
      : undefined,
    originalQuery: data.original_query as string | undefined,
    selectionSource: data.selection_source as string | undefined,
    analysisPhase: data.analysis_phase as TaskInfo['analysisPhase'],
    skills: Array.isArray(data.skills) ? data.skills.map(String) : undefined,
    revision: typeof data.revision === 'number' ? data.revision : undefined,
    updatedAt: data.updated_at as string | undefined,
  };

  if (typeof data.trace_id === 'string' && data.trace_id.trim()) {
    task.traceId = data.trace_id;
  }

  return task;
};

const parseEventData = (eventData: string): ParsedTaskStreamPayload | null => {
  try {
    const data = JSON.parse(eventData);
    const task = toTaskInfo(data);
    const flowEvent = data.flow_event
      ? toCamelCase<RunFlowEvent>(data.flow_event)
      : undefined;
    return { task, flowEvent };
  } catch (e) {
    console.error('Failed to parse SSE event data:', e);
    return null;
  }
};

const notifyConnectionState = (connected: boolean) => {
  sharedConnected = connected;
  subscribers.forEach((subscriber) => subscriber.setIsConnected(connected));
};

const forEachSubscriber = (notify: (callbacks: TaskStreamCallbacks) => void) => {
  subscribers.forEach((subscriber) => notify(subscriber.callbacksRef.current));
};

const isTerminalTask = (task: TaskInfo) => (
  task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled'
);

const isNewerTask = (candidate: TaskInfo, current: TaskInfo): boolean => {
  if (candidate.revision !== undefined && current.revision !== undefined) {
    return candidate.revision > current.revision;
  }
  const candidateTime = candidate.updatedAt ? Date.parse(candidate.updatedAt) : Number.NaN;
  const currentTime = current.updatedAt ? Date.parse(current.updatedAt) : Number.NaN;
  return Number.isFinite(candidateTime) && (!Number.isFinite(currentTime) || candidateTime > currentTime);
};

const getTrackedNonTerminalTasks = (): TaskInfo[] => {
  const byId = new Map<string, TaskInfo>();
  subscribers.forEach((subscriber) => {
    subscriber.trackedTasksRef.current.forEach((task) => {
      if (isTerminalTask(task)) return;
      const existing = byId.get(task.taskId);
      if (!existing || isNewerTask(task, existing)) {
        byId.set(task.taskId, task);
      }
    });
  });
  return Array.from(byId.values());
};

const mergePolledStatus = (task: TaskInfo, status: TaskStatus): TaskInfo => ({
  ...task,
  traceId: status.traceId ?? task.traceId,
  stockName: status.stockName ?? task.stockName,
  status: status.status,
  progress: status.progress ?? task.progress,
  message: status.message ?? task.message,
  messageCode: status.messageCode ?? task.messageCode,
  messageParams: status.messageParams ?? task.messageParams,
  error: status.error ?? task.error,
  errorCode: status.errorCode ?? task.errorCode,
  errorParams: status.errorParams ?? task.errorParams,
  originalQuery: status.originalQuery ?? task.originalQuery,
  selectionSource: status.selectionSource ?? task.selectionSource,
  analysisPhase: status.analysisPhase ?? task.analysisPhase,
  skills: status.skills ?? task.skills,
  revision: status.revision ?? task.revision,
  updatedAt: status.updatedAt ?? task.updatedAt,
  completedAt: isTerminalTask({ ...task, status: status.status })
    ? (status.updatedAt ?? task.completedAt ?? task.updatedAt)
    : task.completedAt,
});

const pollSignature = (task: TaskInfo): string => (
  `${task.updatedAt ?? ''}:${task.startedAt ?? ''}:${task.completedAt ?? ''}:${task.status}:${task.progress}:${task.messageCode ?? ''}:${task.message ?? ''}`
);

const shouldDeliverTask = (task: TaskInfo): boolean => {
  if (task.revision !== undefined) {
    const deliveredRevision = lastDeliveredRevisions.get(task.taskId);
    if (deliveredRevision !== undefined && task.revision <= deliveredRevision) {
      return false;
    }
    lastDeliveredRevisions.set(task.taskId, task.revision);
    lastDeliveredSignatures.set(task.taskId, pollSignature(task));
    return true;
  }
  if (lastDeliveredRevisions.has(task.taskId)) {
    return false;
  }
  const signature = pollSignature(task);
  if (lastDeliveredSignatures.get(task.taskId) === signature) {
    return false;
  }
  lastDeliveredSignatures.set(task.taskId, signature);
  return true;
};

const deliverTask = (task: TaskInfo, notify: (callbacks: TaskStreamCallbacks) => void): boolean => {
  if (!shouldDeliverTask(task)) return false;
  forEachSubscriber(notify);
  return true;
};

const dispatchPolledTask = (task: TaskInfo) => {
  deliverTask(task, (callbacks) => {
    if (task.status === 'completed') {
      callbacks.onTaskCompleted?.(task);
    } else if (task.status === 'failed') {
      callbacks.onTaskFailed?.(task);
    } else {
      callbacks.onTaskProgress?.(task);
    }
  });
};

function stopSharedPolling() {
  if (sharedPollingTimeout) {
    clearTimeout(sharedPollingTimeout);
    sharedPollingTimeout = null;
  }
}

function scheduleSharedPolling() {
  stopSharedPolling();
  if (sharedConnected || subscribers.size === 0 || getTrackedNonTerminalTasks().length === 0) {
    return;
  }
  const delay = Math.min(...Array.from(subscribers.values()).map((subscriber) => subscriber.pollingInterval));
  sharedPollingTimeout = setTimeout(() => {
    sharedPollingTimeout = null;
    void pollTrackedTasks();
  }, delay);
}

async function pollTrackedTasks() {
  if (sharedPollInFlight || sharedConnected || subscribers.size === 0) {
    return;
  }
  const tasks = getTrackedNonTerminalTasks();
  if (tasks.length === 0) {
    return;
  }

  sharedPollInFlight = true;
  try {
    await Promise.all(tasks.map(async (task) => {
      try {
        const status = await analysisApi.getStatus(task.taskId);
        if (
          task.revision !== undefined
          && status.revision !== undefined
          && status.revision < task.revision
        ) {
          return;
        }
        dispatchPolledTask(mergePolledStatus(task, status));
      } catch {
        // Keep polling the other known tasks; one expired task must not stop recovery.
      }
    }));
  } finally {
    sharedPollInFlight = false;
    scheduleSharedPolling();
  }
}

function startSharedPolling() {
  stopSharedPolling();
  void pollTrackedTasks();
}

const clearSharedReconnect = () => {
  if (sharedReconnectTimeout) {
    clearTimeout(sharedReconnectTimeout);
    sharedReconnectTimeout = null;
  }
};

const closeSharedConnection = () => {
  clearSharedReconnect();
  stopSharedPolling();
  if (sharedEventSource) {
    sharedEventSource.close();
    sharedEventSource = null;
  }
  notifyConnectionState(false);
  if (subscribers.size === 0) {
    lastDeliveredSignatures.clear();
    lastDeliveredRevisions.clear();
  }
};

const scheduleSharedReconnect = () => {
  if (sharedReconnectTimeout || subscribers.size === 0) {
    return;
  }
  const reconnectDelays = Array.from(subscribers.values())
    .filter((subscriber) => subscriber.autoReconnect)
    .map((subscriber) => subscriber.reconnectDelay);
  if (reconnectDelays.length === 0) {
    return;
  }
  const reconnectDelay = Math.min(...reconnectDelays);
  sharedReconnectTimeout = setTimeout(() => {
    sharedReconnectTimeout = null;
    connectSharedStream();
  }, reconnectDelay);
};

function connectSharedStream() {
  if (sharedEventSource || subscribers.size === 0) {
    return;
  }

  if (typeof window.EventSource !== 'function') {
    notifyConnectionState(false);
    startSharedPolling();
    return;
  }

  const url = analysisApi.getTaskStreamUrl();
  const eventSource = new window.EventSource(url, { withCredentials: true });
  sharedEventSource = eventSource;

  eventSource.addEventListener('connected', () => {
    stopSharedPolling();
    notifyConnectionState(true);
    forEachSubscriber((callbacks) => callbacks.onConnected?.());
  });

  eventSource.addEventListener('task_created', (e) => {
    const payload = parseEventData((e as MessageEvent<string>).data);
    if (payload) {
      deliverTask(payload.task, (callbacks) => callbacks.onTaskCreated?.(payload.task));
    }
  });

  eventSource.addEventListener('task_started', (e) => {
    const payload = parseEventData((e as MessageEvent<string>).data);
    if (payload) {
      deliverTask(payload.task, (callbacks) => callbacks.onTaskStarted?.(payload.task));
    }
  });

  eventSource.addEventListener('task_progress', (e) => {
    const payload = parseEventData((e as MessageEvent<string>).data);
    if (payload) {
      deliverTask(payload.task, (callbacks) => {
        callbacks.onTaskProgress?.(payload.task);
        if (payload.flowEvent) {
          callbacks.onTaskFlowEvent?.(payload.task, payload.flowEvent);
        }
      });
    }
  });

  eventSource.addEventListener('task_completed', (e) => {
    const payload = parseEventData((e as MessageEvent<string>).data);
    if (payload) {
      deliverTask(payload.task, (callbacks) => callbacks.onTaskCompleted?.(payload.task));
    }
  });

  eventSource.addEventListener('task_failed', (e) => {
    const payload = parseEventData((e as MessageEvent<string>).data);
    if (payload) {
      deliverTask(payload.task, (callbacks) => callbacks.onTaskFailed?.(payload.task));
    }
  });

  eventSource.addEventListener('heartbeat', () => {
    // Optional place to record the latest heartbeat timestamp.
  });

  eventSource.onerror = (error) => {
    notifyConnectionState(false);
    forEachSubscriber((callbacks) => callbacks.onError?.(error));
    if (sharedEventSource === eventSource) {
      eventSource.close();
      sharedEventSource = null;
    }
    startSharedPolling();
    scheduleSharedReconnect();
  };
}

const reconnectSharedStream = () => {
  closeSharedConnection();
  connectSharedStream();
};

/**
 * Task-stream SSE hook for realtime task status updates.
 */
export function useTaskStream(options: UseTaskStreamOptions = {}): UseTaskStreamResult {
  const {
    onTaskCreated,
    onTaskStarted,
    onTaskCompleted,
    onTaskProgress,
    onTaskFailed,
    onTaskFlowEvent,
    onConnected,
    onError,
    autoReconnect = true,
    reconnectDelay = 3000,
    enabled = true,
    trackedTasks = [],
    pollingInterval = 2000,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const subscriberIdRef = useRef<number | null>(null);
  const connectTimerRef = useRef<number | null>(null);
  const trackedTasksRef = useRef<readonly TaskInfo[]>(trackedTasks);

  // Store callbacks in a ref to avoid reconnecting on every render.
  const callbacksRef = useRef<TaskStreamCallbacks>({
    onTaskCreated,
    onTaskStarted,
    onTaskCompleted,
    onTaskProgress,
    onTaskFailed,
    onTaskFlowEvent,
    onConnected,
    onError,
  });

  // Keep the latest callbacks available to the active SSE handlers.
  useEffect(() => {
    callbacksRef.current = {
      onTaskCreated,
      onTaskStarted,
      onTaskCompleted,
      onTaskProgress,
      onTaskFailed,
      onTaskFlowEvent,
      onConnected,
      onError,
    };
  });

  useEffect(() => {
    trackedTasksRef.current = trackedTasks;
  }, [trackedTasks]);

  // Disconnect and defer the state update to avoid nested renders.
  const disconnect = useCallback(() => {
    if (connectTimerRef.current) {
      window.clearTimeout(connectTimerRef.current);
      connectTimerRef.current = null;
    }
    if (subscriberIdRef.current !== null) {
      subscribers.delete(subscriberIdRef.current);
      subscriberIdRef.current = null;
    }
    if (subscribers.size === 0) {
      closeSharedConnection();
    }
    queueMicrotask(() => setIsConnected(false));
  }, []);

  // Reconnect
  const reconnect = useCallback(() => {
    if (subscriberIdRef.current === null) {
      const subscriberId = nextSubscriberId++;
      subscriberIdRef.current = subscriberId;
      subscribers.set(subscriberId, {
        callbacksRef,
        setIsConnected,
        autoReconnect,
        reconnectDelay,
        trackedTasksRef,
        pollingInterval,
      });
    }
    reconnectSharedStream();
  }, [autoReconnect, pollingInterval, reconnectDelay]);

  // Connect or disconnect when the hook is enabled or disabled.
  useEffect(() => {
    if (enabled) {
      const subscriberId = nextSubscriberId++;
      subscriberIdRef.current = subscriberId;
      subscribers.set(subscriberId, {
        callbacksRef,
        setIsConnected,
        autoReconnect,
        reconnectDelay,
        trackedTasksRef,
        pollingInterval,
      });
      setIsConnected(sharedConnected);
      connectTimerRef.current = window.setTimeout(() => {
        connectTimerRef.current = null;
        connectSharedStream();
      }, 0);
      return () => {
        disconnect();
      };
    }

    disconnect();
    return () => {
      disconnect();
    };
  }, [autoReconnect, disconnect, enabled, pollingInterval, reconnectDelay]);

  return {
    isConnected,
    reconnect,
    disconnect,
  };
}

export default useTaskStream;
