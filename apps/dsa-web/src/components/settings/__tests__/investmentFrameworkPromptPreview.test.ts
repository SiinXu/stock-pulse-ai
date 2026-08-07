// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { InvestmentFrameworkContent } from '../../../types/investmentFramework';
import {
  formatInvestmentFrameworkPromptPreview,
  hasFrameworkPromptPreviewContent,
} from '../investmentFrameworkPromptPreviewModel';

function sampleContent(): InvestmentFrameworkContent {
  return {
    schemaVersion: 'investment-framework-content-v1',
    title: 'Quality first',
    freeFormRules: 'Prefer durable cash flow',
    riskRules: ['Cap single-name size at 10%'],
    trackingCriteria: ['Review earnings revisions'],
    rootNodeId: 'root',
    decisionTree: [
      {
        nodeId: 'root',
        question: 'Is the moat durable?',
        branches: [
          { condition: 'Yes', targetNodeId: 'valuation', outcome: null },
          { condition: 'No', targetNodeId: null, outcome: 'Pass' },
        ],
      },
      {
        nodeId: 'valuation',
        question: 'Is valuation attractive?',
        branches: [
          { condition: 'Yes', targetNodeId: null, outcome: 'Track' },
        ],
      },
    ],
    evaluationDimensions: [
      { name: 'Moat', weight: 50, criteria: ['Pricing power'] },
    ],
  };
}

describe('investmentFrameworkPromptPreview', () => {
  it('returns empty when there is no substantive draft content', () => {
    expect(hasFrameworkPromptPreviewContent({
      title: '',
      riskRules: [],
      trackingCriteria: [],
    })).toBe(false);
    expect(formatInvestmentFrameworkPromptPreview({
      title: '',
      riskRules: [],
      trackingCriteria: [],
    })).toBe('');
  });

  it('mirrors English analysis prompt phrasing including the decision tree', () => {
    const section = formatInvestmentFrameworkPromptPreview(sampleContent(), {
      frameworkId: 7,
      frameworkVersion: 3,
      draft: false,
      reportLanguage: 'en',
    });
    expect(section).toContain('## Personal Investment Framework (read-only)');
    expect(section).toContain('Title: Quality first');
    expect(section).toContain('Framework ID: 7');
    expect(section).toContain('Content version: 3');
    expect(section).toContain('Prefer durable cash flow');
    expect(section).toContain('Cap single-name size at 10%');
    expect(section).toContain('Moat (weight 50): Pricing power');
    expect(section).toContain('### Decision tree');
    expect(section).toContain('Root: root');
    expect(section).toContain('[root] Is the moat durable?');
    expect(section).toContain('if Yes: → valuation');
    expect(section).toContain('if No: ⇒ Pass');
  });

  it('uses draft placeholders and Chinese headings for zh preview', () => {
    const section = formatInvestmentFrameworkPromptPreview(sampleContent(), {
      draft: true,
      reportLanguage: 'zh',
    });
    expect(section).toContain('## 个人投资框架（只读）');
    expect(section).toContain('框架 ID：草稿');
    expect(section).toContain('内容版本：未保存');
    expect(section).toContain('### 决策树');
    expect(section).toContain('根节点：root');
  });

  it('clips oversized free-form rules like the backend helper', () => {
    const section = formatInvestmentFrameworkPromptPreview(
      {
        title: 'Huge',
        freeFormRules: 'A'.repeat(5000),
      },
      { draft: true, reportLanguage: 'en' },
    );
    expect(section).not.toContain('A'.repeat(5000));
    expect(section).toContain('…');
    expect(section.length).toBeLessThan(4000);
  });
});
