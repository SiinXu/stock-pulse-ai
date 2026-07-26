export type ScheduledTaskType =
  | 'stock_analysis'
  | 'research_brief'
  | 'risk_check'
  | string;

export type ScheduledTaskOccurrenceStatus =
  | 'scheduled'
  | 'dispatching'
  | 'running'
  | 'retry_wait'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'interrupted';

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
  status: Exclude<ScheduledTaskOccurrenceStatus, 'scheduled'>;
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
