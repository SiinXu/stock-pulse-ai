import type { Message, ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';

export const getMessageSkillNames = (msg: Message): string[] => {
  if (msg.skillNames?.length) return msg.skillNames;
  if (msg.skillName) return [msg.skillName];
  if (msg.skills?.length) return msg.skills;
  if (msg.skill) return [msg.skill];
  return [];
};

export const getMessageSkillLabel = (msg: Message): string => getMessageSkillNames(msg).join('、');

export const isStageDoneSuccessful = (status?: string): boolean => {
  if (!status) return true;
  const normalized = status.trim().toLowerCase();
  return ['completed', 'success', 'succeeded', 'done'].includes(normalized);
};

export const getStageDoneLabel = (step: ProgressStep): string => {
  const stage = step.stage || 'stage';
  if (step.message) return step.message;
  if (isStageDoneSuccessful(step.status)) return `${stage} completed`;
  return `${stage} ${step.status || 'finished'}`;
};

export const getPipelineBudgetSkippedLabel = (step: ProgressStep): string => {
  if (step.message) return step.message;
  return `${step.stage || 'pipeline'} skipped: insufficient budget`;
};

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export function getCurrentStageLabel(
  steps: ProgressStep[],
  t: Translate,
): string {
  if (steps.length === 0) return t('chat.connecting');
  const last = steps[steps.length - 1];
  if (last.type === 'thinking') return last.message || t('chat.thinking');
  if (last.type === 'tool_start') return `${last.display_name || last.tool}...`;
  if (last.type === 'tool_done') {
    return t('chat.completed', { name: last.display_name || last.tool || '' });
  }
  if (last.type === 'stage_start') {
    return last.message || `Starting ${last.stage || 'stage'}...`;
  }
  if (last.type === 'stage_done') return getStageDoneLabel(last);
  if (last.type === 'pipeline_timeout') {
    return last.message || `${last.stage || 'pipeline'} timed out`;
  }
  if (last.type === 'pipeline_budget_skipped') {
    return getPipelineBudgetSkippedLabel(last);
  }
  if (last.type === 'generating') return last.message || t('chat.generating');
  return t('chat.processing');
}
