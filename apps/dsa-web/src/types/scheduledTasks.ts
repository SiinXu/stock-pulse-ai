export type ScheduledTaskType =
  | 'stock_analysis'
  | 'research_brief'
  | 'risk_check'
  | string;

export type ScheduledTaskSupportedType =
  | 'stock_analysis'
  | 'research_brief'
  | 'risk_check';

export type ScheduledTaskReportType = 'brief' | 'simple' | 'detailed' | 'full';

export type ScheduledTaskCalendarMarket = 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';

export type ScheduledTaskNonTradingDayPolicy = 'skip' | 'run';

export type ScheduledTaskOccurrenceStatus =
  | 'scheduled'
  | 'dispatching'
  | 'running'
  | 'retry_wait'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'interrupted';

export type ScheduledTaskRunStatus = Exclude<ScheduledTaskOccurrenceStatus, 'scheduled'>;

export type ScheduledTaskCompatibility = 'supported' | 'unsupported_schema';

export interface ScheduledTaskDefinitionSummary {
  compatibility: ScheduledTaskCompatibility;
  id: string;
  schemaVersion: number;
  name: string;
  taskType?: ScheduledTaskType;
  enabled: boolean;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Present on OpenAPI ScheduledTaskItem (supported); omitted for unsupported_schema. */
  maxAttempts?: number;
}

export interface ScheduledTaskListResponse {
  items: ScheduledTaskDefinitionSummary[];
  total: number;
}

export interface ScheduledTaskListQuery {
  enabled?: boolean;
  limit?: number;
}

export interface ScheduledTaskRunSummary {
  id: string;
  status: ScheduledTaskRunStatus;
  errorCode: string | null;
}

export interface ScheduledTaskTodayItem {
  task: ScheduledTaskDefinitionSummary;
  scheduledFor: string;
  status: ScheduledTaskOccurrenceStatus;
  run: ScheduledTaskRunSummary | null;
}

export interface ScheduledTaskTodayResponse {
  date: string;
  timezone: string;
  generatedAt: string;
  items: ScheduledTaskTodayItem[];
  total: number;
}

export interface ScheduledTaskTodayQuery {
  timezone?: string;
}

export interface ScheduledTaskDailySchedule {
  kind: 'daily';
  time: string;
  timezone: string;
  calendarMarket: ScheduledTaskCalendarMarket;
  nonTradingDayPolicy: ScheduledTaskNonTradingDayPolicy;
}

export interface ScheduledTaskStockAnalysisPayload {
  stockCode: string;
  reportType?: ScheduledTaskReportType;
  notify?: boolean;
}

export interface ScheduledTaskResearchPayload {
  stockCode: string;
  notify?: boolean;
}

export interface ScheduledTaskCreateRequest {
  schemaVersion: 1 | 2;
  name: string;
  taskType: ScheduledTaskSupportedType;
  schedule: ScheduledTaskDailySchedule;
  payload: ScheduledTaskStockAnalysisPayload | ScheduledTaskResearchPayload;
  enabled?: boolean;
  maxAttempts?: number;
}

export interface ScheduledTaskRunItem {
  id: string;
  taskId: string;
  scheduledFor: string;
  status: ScheduledTaskRunStatus;
  attemptCount: number;
  dispatchFailureCount: number;
  executionTaskIds: string[];
  resultRefs: string[];
  notificationStatus?: string | null;
  notificationChannels?: string[];
  notificationFailedChannels?: string[];
  errorCode: string | null;
  nextAttemptAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ScheduledTaskRunListResponse {
  items: ScheduledTaskRunItem[];
  total: number;
}

export interface ScheduledTaskRunListQuery {
  limit?: number;
}

export interface ScheduledTaskStatusResponse {
  task: ScheduledTaskDefinitionSummary;
  latestRun: ScheduledTaskRunItem | null;
}
