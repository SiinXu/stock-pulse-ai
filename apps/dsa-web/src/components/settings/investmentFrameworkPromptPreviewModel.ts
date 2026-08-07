// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client-side mirror of src/services/investment_framework_prompt.py
 * format_investment_framework_prompt_section so the Settings editor can
 * preview how criteria phrase into stock-analysis context.
 *
 * Keep budgets and section order aligned with the backend helper.
 */
import type { InvestmentFrameworkContent } from '../../types/investmentFramework';

/** Prompt-only budgets (must match investment_framework_prompt.py). */
export const FRAMEWORK_PROMPT_PREVIEW_BUDGETS = {
  freeFormMaxChars: 2500,
  listMaxItems: 20,
  listItemMaxChars: 400,
  dimensionMaxItems: 15,
  descriptionMaxChars: 800,
  treeMaxNodes: 12,
  treeMaxBranches: 8,
  treeFieldMaxChars: 200,
} as const;

export type FrameworkPromptPreviewLanguage = 'zh' | 'en';

export type FrameworkPromptPreviewMeta = {
  frameworkId?: number | null;
  frameworkVersion?: number | null;
  /** When true, meta uses draft placeholders for id/version. */
  draft?: boolean;
};

function clipText(value: string, limit: number): string {
  const text = (value || '').trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, Math.max(0, limit - 1)).replace(/\s+$/u, '')}…`;
}

function clipRuleList(values: readonly string[] | undefined): string[] {
  const clipped: string[] = [];
  for (const item of (values ?? []).slice(0, FRAMEWORK_PROMPT_PREVIEW_BUDGETS.listMaxItems)) {
    const cleaned = clipText(String(item), FRAMEWORK_PROMPT_PREVIEW_BUDGETS.listItemMaxChars);
    if (cleaned) {
      clipped.push(cleaned);
    }
  }
  return clipped;
}

function formatDecisionTreeLines(
  content: InvestmentFrameworkContent,
  english: boolean,
): string[] {
  const nodes = content.decisionTree ?? [];
  if (!nodes.length) {
    return [];
  }
  const lines: string[] = [english ? '### Decision tree' : '### 决策树'];
  if (content.rootNodeId) {
    const root = clipText(String(content.rootNodeId), FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars);
    lines.push(english ? `- Root: ${root}` : `- 根节点：${root}`);
  }
  for (const node of nodes.slice(0, FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeMaxNodes)) {
    const nodeId = clipText(String(node.nodeId || ''), FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars);
    const question = clipText(
      String(node.question || ''),
      FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars,
    );
    if (!nodeId && !question) {
      continue;
    }
    const label = nodeId ? `[${nodeId}] ${question}`.trim() : question;
    lines.push(`- ${label}`);
    for (const branch of (node.branches ?? []).slice(
      0,
      FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeMaxBranches,
    )) {
      const condition = clipText(
        String(branch.condition || ''),
        FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars,
      );
      let dest: string;
      if (branch.targetNodeId) {
        dest = `→ ${clipText(String(branch.targetNodeId), FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars)}`;
      } else if (branch.outcome) {
        dest = `⇒ ${clipText(String(branch.outcome), FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeFieldMaxChars)}`;
      } else {
        dest = english ? '→ ?' : '→ ？';
      }
      if (condition) {
        lines.push(english ? `  - if ${condition}: ${dest}` : `  - 若 ${condition}：${dest}`);
      } else {
        lines.push(`  - ${dest}`);
      }
    }
  }
  if (nodes.length > FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeMaxNodes) {
    const omitted = nodes.length - FRAMEWORK_PROMPT_PREVIEW_BUDGETS.treeMaxNodes;
    lines.push(
      english
        ? `- … and ${omitted} more node(s)`
        : `- … 另有 ${omitted} 个节点未展开`,
    );
  }
  lines.push('');
  return lines;
}

/**
 * Returns true when the draft would produce a non-empty prompt section after
 * activation (at least a title plus any substantive criterion).
 */
export function hasFrameworkPromptPreviewContent(
  content: InvestmentFrameworkContent,
): boolean {
  if ((content.title ?? '').trim()) {
    return true;
  }
  if ((content.description ?? '').trim()) {
    return true;
  }
  if ((content.freeFormRules ?? '').trim()) {
    return true;
  }
  if ((content.riskRules ?? []).some((item) => String(item).trim())) {
    return true;
  }
  if ((content.trackingCriteria ?? []).some((item) => String(item).trim())) {
    return true;
  }
  if ((content.evaluationDimensions ?? []).length > 0) {
    return true;
  }
  if ((content.decisionTree ?? []).length > 0) {
    return true;
  }
  return false;
}

/**
 * Mirror of backend format_investment_framework_prompt_section.
 * Empty string when there is nothing meaningful to preview.
 */
export function formatInvestmentFrameworkPromptPreview(
  content: InvestmentFrameworkContent,
  options: FrameworkPromptPreviewMeta & {
    reportLanguage?: FrameworkPromptPreviewLanguage | string;
  } = {},
): string {
  if (!hasFrameworkPromptPreviewContent(content)) {
    return '';
  }

  const english = (options.reportLanguage ?? 'zh') === 'en'
    || (options.reportLanguage ?? 'zh') === 'ko';
  const title = (content.title || '').trim() || (english ? '(untitled draft)' : '（未命名草稿）');
  const frameworkId = options.draft || options.frameworkId == null
    ? (english ? 'draft' : '草稿')
    : String(options.frameworkId);
  const version = options.draft || options.frameworkVersion == null
    ? (english ? 'unsaved' : '未保存')
    : String(options.frameworkVersion);

  const description = clipText(
    content.description ?? '',
    FRAMEWORK_PROMPT_PREVIEW_BUDGETS.descriptionMaxChars,
  );
  const freeForm = clipText(
    content.freeFormRules ?? '',
    FRAMEWORK_PROMPT_PREVIEW_BUDGETS.freeFormMaxChars,
  );
  const riskRules = clipRuleList(content.riskRules);
  const trackingCriteria = clipRuleList(content.trackingCriteria);
  const dimensions = (content.evaluationDimensions ?? []).slice(
    0,
    FRAMEWORK_PROMPT_PREVIEW_BUDGETS.dimensionMaxItems,
  );

  if (english) {
    const lines = [
      '## Personal Investment Framework (read-only)',
      '',
      `- Title: ${title}`,
      `- Framework ID: ${frameworkId}`,
      `- Content version: ${version}`,
      '',
      'Use this framework only as research context. Do not treat it as live '
      + 'trading authority or investment advice.',
      '',
    ];
    if (description) {
      lines.push('### Description', description, '');
    }
    if (freeForm) {
      lines.push('### Free-form rules', freeForm, '');
    }
    if (riskRules.length) {
      lines.push('### Risk rules');
      lines.push(...riskRules.map((rule) => `- ${rule}`));
      lines.push('');
    }
    if (trackingCriteria.length) {
      lines.push('### Tracking criteria');
      lines.push(...trackingCriteria.map((item) => `- ${item}`));
      lines.push('');
    }
    if (dimensions.length) {
      lines.push('### Evaluation dimensions');
      for (const dimension of dimensions) {
        const criteria = clipRuleList(dimension.criteria).join('; ');
        lines.push(
          `- ${dimension.name} (weight ${dimension.weight})`
          + (criteria ? `: ${criteria}` : ''),
        );
      }
      lines.push('');
    }
    lines.push(...formatDecisionTreeLines(content, true));
    return lines.join('\n');
  }

  const lines = [
    '## 个人投资框架（只读）',
    '',
    `- 名称：${title}`,
    `- 框架 ID：${frameworkId}`,
    `- 内容版本：${version}`,
    '',
    '以下内容仅作为研究上下文参考，不构成投资建议，也不授权自动交易。',
    '',
  ];
  if (description) {
    lines.push('### 说明', description, '');
  }
  if (freeForm) {
    lines.push('### 自由规则', freeForm, '');
  }
  if (riskRules.length) {
    lines.push('### 风险规则');
    lines.push(...riskRules.map((rule) => `- ${rule}`));
    lines.push('');
  }
  if (trackingCriteria.length) {
    lines.push('### 跟踪条件');
    lines.push(...trackingCriteria.map((item) => `- ${item}`));
    lines.push('');
  }
  if (dimensions.length) {
    lines.push('### 评估维度');
    for (const dimension of dimensions) {
      const criteria = clipRuleList(dimension.criteria).join('；');
      lines.push(
        `- ${dimension.name}（权重 ${dimension.weight}）`
        + (criteria ? `：${criteria}` : ''),
      );
    }
    lines.push('');
  }
  lines.push(...formatDecisionTreeLines(content, false));
  return lines.join('\n');
}
