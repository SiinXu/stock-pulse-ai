import type { UiTextKey, UiTextParams } from '../i18n/uiText';
import type { TaskInfo } from '../types/analysis';

type Translate = (key: UiTextKey, params?: UiTextParams) => string;
export type TaskMessageLike = Pick<TaskInfo, 'status' | 'messageCode' | 'messageParams'>;

const MESSAGE_KEYS: Record<string, UiTextKey> = {
  task_queued: 'taskPanel.message.queued',
  task_started: 'taskPanel.message.started',
  task_progress: 'taskPanel.message.progress',
  task_completed: 'taskPanel.message.completed',
  task_failed: 'taskPanel.message.failed',
  alphasift_screen_queued: 'taskPanel.message.screeningQueued',
  alphasift_screen_running: 'taskPanel.message.screeningRunning',
  alphasift_screen_formatting: 'taskPanel.message.screeningFormatting',
};

const FALLBACK_KEYS: Record<TaskInfo['status'], UiTextKey> = {
  pending: 'taskPanel.message.queued',
  processing: 'taskPanel.message.processingGeneric',
  completed: 'taskPanel.message.completed',
  failed: 'taskPanel.message.failed',
  cancel_requested: 'taskPanel.message.cancelRequested',
  cancelled: 'taskPanel.message.cancelled',
};

function toUiTextParams(params?: Record<string, unknown>): UiTextParams | undefined {
  if (!params) return undefined;
  const safe = Object.entries(params).flatMap(([key, value]) => (
    typeof value === 'string' || typeof value === 'number' ? [[key, value] as const] : []
  ));
  return Object.fromEntries(safe);
}

export function localizeTaskMessage(task: TaskMessageLike, t: Translate): string {
  const key = task.messageCode ? MESSAGE_KEYS[task.messageCode] : undefined;
  return t(key ?? FALLBACK_KEYS[task.status], toUiTextParams(task.messageParams));
}
