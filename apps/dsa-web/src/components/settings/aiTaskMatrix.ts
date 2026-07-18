// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import { localeIndependent, type UiLanguage } from '../../i18n/uiLanguages';
// Resolves the effective AI routing for each user-facing task into a matrix the
// AI Overview renders, so users see execution backend + models per task without
// reading env vars or internal route aliases.

export type UiLang = UiLanguage;

type BilingualLabel = Record<UiLanguage, string>;

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
  litellm: createUiLanguageRecord("components.settings.aiTaskMatrix.BACKEND_LABELS.litellm", { zh: 'LiteLLM（云 API）', en: 'LiteLLM (cloud API)' }),
  codex_cli: createUiLanguageRecord("components.settings.aiTaskMatrix.BACKEND_LABELS.codex_cli", { zh: 'Codex CLI（本地）', en: 'Codex CLI (local)' }),
  claude_code_cli: createUiLanguageRecord("components.settings.aiTaskMatrix.BACKEND_LABELS.claude_code_cli", { zh: 'Claude Code CLI（本地）', en: 'Claude Code CLI (local)' }),
  opencode_cli: createUiLanguageRecord("components.settings.aiTaskMatrix.BACKEND_LABELS.opencode_cli", { zh: 'OpenCode CLI（本地）', en: 'OpenCode CLI (local)' }),
};

const NOT_CONFIGURED_LABEL = createUiLanguageRecord('components.settings.aiTaskMatrix.NOT_CONFIGURED_LABEL', {
  zh: '未配置',
  en: 'Not configured',
});

const TASK_LABELS = {
  report: createUiLanguageRecord('components.settings.aiTaskMatrix.TASK_LABELS.report', { zh: '股票报告', en: 'Stock report' }),
  market_review: createUiLanguageRecord('components.settings.aiTaskMatrix.TASK_LABELS.market_review', { zh: '大盘复盘', en: 'Market review' }),
  agent: createUiLanguageRecord('components.settings.aiTaskMatrix.TASK_LABELS.agent', { zh: '问股 / Agent', en: 'Ask / Agent' }),
  vision: localeIndependent('Vision'),
} satisfies Record<string, BilingualLabel>;

function backendLabel(id: string): BilingualLabel {
  return BACKEND_LABELS[id] ?? (id ? localeIndependent(id) : NOT_CONFIGURED_LABEL);
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
    row('report', TASK_LABELS.report, reportModel, false, fallbackModels),
    row('market_review', TASK_LABELS.market_review, reportModel, true, fallbackModels),
    row('agent', TASK_LABELS.agent, agentModel || reportModel, agentModel.length === 0, fallbackModels),
    row('vision', TASK_LABELS.vision, visionModel || reportModel, visionModel.length === 0, []),
  ];
}
