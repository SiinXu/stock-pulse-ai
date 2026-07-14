// Resolves the effective AI routing for each user-facing task into a matrix the
// AI Overview renders, so users see execution backend + models per task without
// reading env vars or internal route aliases.

export type UiLang = 'zh' | 'en';

interface BilingualLabel {
  zh: string;
  en: string;
}

export type AiTaskStatus = 'active' | 'unavailable' | 'unconfigured';

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
  /**
   * Authoritative status: 'active' when the effective model is declared by an
   * enabled connection in the active source (routable); 'unavailable' when a
   * model is set but not routable by the current config; 'unconfigured' when no
   * model is set. Falls back to non-empty when no route set is provided.
   */
  status: AiTaskStatus;
  /** Back-compat: true when the effective model is active/routable. */
  active: boolean;
}

interface ResolveOptions {
  /** Authoritative set of model routes declared by enabled connections. */
  availableRoutes?: Set<string>;
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
export function resolveAiTaskMatrix(
  get: (key: string) => string,
  options: ResolveOptions = {},
): AiTaskRow[] {
  const { availableRoutes } = options;
  const backendId = (get('GENERATION_BACKEND') || 'litellm').trim();
  const fallbackBackendId = (get('GENERATION_FALLBACK_BACKEND') || '').trim();
  const reportModel = get('LITELLM_MODEL').trim();
  const agentModel = get('AGENT_LITELLM_MODEL').trim();
  const visionModel = get('VISION_MODEL').trim();
  const fallbackModels = splitModels(get('LITELLM_FALLBACK_MODELS'));
  const label = backendLabel(backendId);
  // Local CLI backends run without a channel model, so their route set is not
  // meaningful — treat a selected CLI backend as active on its own.
  const isCliBackend = backendId !== 'litellm' && backendId.length > 0;

  const resolveStatus = (model: string): AiTaskStatus => {
    if (isCliBackend) {
      return 'active';
    }
    if (model.length === 0) {
      return 'unconfigured';
    }
    if (availableRoutes) {
      return availableRoutes.has(model) ? 'active' : 'unavailable';
    }
    return 'active';
  };

  const row = (
    id: string,
    labelText: BilingualLabel,
    model: string,
    inherited: boolean,
    fallbacks: string[],
  ): AiTaskRow => {
    const status = resolveStatus(model);
    return {
      id,
      label: labelText,
      backendId,
      backendLabel: label,
      fallbackBackendId,
      primaryModel: model,
      primaryInherited: inherited,
      fallbackModels: fallbacks,
      status,
      active: status === 'active',
    };
  };

  return [
    row('report', { zh: '股票报告', en: 'Stock report' }, reportModel, false, fallbackModels),
    row('market_review', { zh: '大盘复盘', en: 'Market review' }, reportModel, true, fallbackModels),
    row('agent', { zh: '问股 / Agent', en: 'Ask / Agent' }, agentModel || reportModel, agentModel.length === 0, fallbackModels),
    row('vision', { zh: 'Vision', en: 'Vision' }, visionModel || reportModel, visionModel.length === 0, []),
  ];
}
