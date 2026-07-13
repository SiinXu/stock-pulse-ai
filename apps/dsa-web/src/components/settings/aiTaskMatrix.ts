// Resolves the effective AI routing for each user-facing task into a matrix the
// AI Overview renders, so users see execution backend + models per task without
// reading env vars or internal route aliases.

export type UiLang = 'zh' | 'en';

interface BilingualLabel {
  zh: string;
  en: string;
}

export interface AiTaskRow {
  id: string;
  label: BilingualLabel;
  /** Execution backend id (raw config value), e.g. 'litellm' / 'codex_cli'. */
  backendId: string;
  backendLabel: BilingualLabel;
  /** Optional failover execution backend id. */
  fallbackBackendId: string;
  primaryModel: string;
  /** True when the task has no dedicated model and inherits the report model. */
  primaryInherited: boolean;
  fallbackModels: string[];
  /** Whether an effective model is resolved (configured & routable). */
  active: boolean;
}

const BACKEND_LABELS: Record<string, BilingualLabel> = {
  litellm: { zh: 'LiteLLM（云 API）', en: 'LiteLLM (cloud API)' },
  codex_cli: { zh: 'Codex CLI（本地）', en: 'Codex CLI (local)' },
  claude_code_cli: { zh: 'Claude Code CLI（本地）', en: 'Claude Code CLI (local)' },
  opencode_cli: { zh: 'OpenCode CLI（本地）', en: 'OpenCode CLI (local)' },
};

function backendLabel(id: string): BilingualLabel {
  return BACKEND_LABELS[id] ?? { zh: id || '未配置', en: id || 'Not configured' };
}

function splitModels(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

/**
 * Build the task matrix from a config value accessor. Market review inherits the
 * report model; agent and vision inherit it only when they have no dedicated
 * model configured, mirroring the runtime resolution order.
 */
export function resolveAiTaskMatrix(get: (key: string) => string): AiTaskRow[] {
  const backendId = (get('GENERATION_BACKEND') || 'litellm').trim();
  const fallbackBackendId = (get('GENERATION_FALLBACK_BACKEND') || '').trim();
  const reportModel = get('LITELLM_MODEL').trim();
  const agentModel = get('AGENT_LITELLM_MODEL').trim();
  const visionModel = get('VISION_MODEL').trim();
  const fallbackModels = splitModels(get('LITELLM_FALLBACK_MODELS'));
  const label = backendLabel(backendId);

  const row = (
    id: string,
    labelText: BilingualLabel,
    model: string,
    inherited: boolean,
    fallbacks: string[],
  ): AiTaskRow => ({
    id,
    label: labelText,
    backendId,
    backendLabel: label,
    fallbackBackendId,
    primaryModel: model,
    primaryInherited: inherited,
    fallbackModels: fallbacks,
    active: model.length > 0,
  });

  return [
    row('report', { zh: '股票报告', en: 'Stock report' }, reportModel, false, fallbackModels),
    row('market_review', { zh: '大盘复盘', en: 'Market review' }, reportModel, true, fallbackModels),
    row('agent', { zh: '问股 / Agent', en: 'Ask / Agent' }, agentModel || reportModel, agentModel.length === 0, fallbackModels),
    row('vision', { zh: 'Vision', en: 'Vision' }, visionModel || reportModel, visionModel.length === 0, []),
  ];
}
