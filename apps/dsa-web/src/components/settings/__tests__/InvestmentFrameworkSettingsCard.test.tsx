// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { formatDateTime } from '../../../utils/format';
import { InvestmentFrameworkSettingsCard } from '../InvestmentFrameworkSettingsCard';

const {
  getFramework,
  createFramework,
  updateFramework,
  deactivateFramework,
  removeFramework,
  historyFramework,
} = vi.hoisted(() => ({
  getFramework: vi.fn(),
  createFramework: vi.fn(),
  updateFramework: vi.fn(),
  deactivateFramework: vi.fn(),
  removeFramework: vi.fn(),
  historyFramework: vi.fn(),
}));

vi.mock('../../../api/investmentFramework', () => ({
  investmentFrameworkApi: {
    get: getFramework,
    create: createFramework,
    update: updateFramework,
    deactivate: deactivateFramework,
    remove: removeFramework,
    history: historyFramework,
  },
}));

describe('InvestmentFrameworkSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    historyFramework.mockResolvedValue({
      frameworkId: 1,
      latestVersion: 0,
      activeVersion: null,
      revision: 0,
      items: [],
      total: 0,
    });
  });

  it('creates a framework when none exists', async () => {
    getFramework.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: 'Not found',
          message: 'missing',
          rawMessage: 'missing',
          status: 404,
          category: 'http_error',
          code: 'investment_framework_not_found',
        }),
      ),
    );
    createFramework.mockResolvedValue({
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 1,
      isActive: true,
      content: {
        title: 'My rules',
        freeFormRules: 'Prefer quality businesses',
        riskRules: [],
        trackingCriteria: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    });

    render(<InvestmentFrameworkSettingsCard />);

    await waitFor(() => {
      expect(getFramework).toHaveBeenCalled();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByLabelText('框架名称')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '版本历史' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('框架名称'), { target: { value: 'My rules' } });
    fireEvent.change(screen.getByLabelText('自由规则'), {
      target: { value: 'Prefer quality businesses' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建框架' }));

    await waitFor(() => {
      expect(createFramework).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.objectContaining({
            title: 'My rules',
            freeFormRules: 'Prefer quality businesses',
          }),
        }),
      );
    });
    expect(await screen.findByText('个人投资框架已创建并激活')).toBeInTheDocument();
  });

  it('keeps a failed framework read distinct from a missing framework', async () => {
    getFramework.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '框架加载失败',
          message: '暂时无法读取个人投资框架。',
          rawMessage: 'framework unavailable',
          status: 500,
          category: 'http_error',
          code: 'framework_load_failed',
        }),
      ),
    );

    render(<InvestmentFrameworkSettingsCard />);

    expect(await screen.findByText('暂时无法读取个人投资框架。')).toBeInTheDocument();
    expect(screen.queryByText('未配置')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '版本历史' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
    expect(createFramework).not.toHaveBeenCalled();
  });

  it('saves a new version with optimistic concurrency', async () => {
    getFramework.mockResolvedValue({
      frameworkId: 1,
      scope: 'local',
      version: 2,
      activeVersion: 2,
      revision: 3,
      isActive: true,
      content: {
        title: 'Existing',
        freeFormRules: 'Hold cash when uncertain',
        riskRules: ['Max 10% per name'],
        trackingCriteria: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    });
    const updatedFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 3,
      activeVersion: 3,
      revision: 4,
      isActive: true,
      content: {
        title: 'Existing',
        freeFormRules: 'Updated free form',
        riskRules: ['Max 10% per name'],
        trackingCriteria: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T01:00:00Z',
      versionCreatedAt: '2026-07-26T01:00:00Z',
    };
    let resolveUpdate!: (value: typeof updatedFramework) => void;
    updateFramework.mockReturnValue(new Promise((resolve) => {
      resolveUpdate = resolve;
    }));

    render(<InvestmentFrameworkSettingsCard />);

    await screen.findByDisplayValue('Existing');
    fireEvent.change(screen.getByLabelText('自由规则'), {
      target: { value: 'Updated free form' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => {
      expect(updateFramework).toHaveBeenCalledWith(
        expect.objectContaining({
          expectedRevision: 3,
          content: expect.objectContaining({ freeFormRules: 'Updated free form' }),
        }),
      );
    });
    expect(screen.getByDisplayValue('Updated free form').closest('form'))
      .toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('处理中...');
    expect(screen.getByRole('button', { name: '保存新版本' })).toBeDisabled();
    await act(async () => {
      resolveUpdate(updatedFramework);
    });
    expect(await screen.findByText('已保存为新版本并激活')).toBeInTheDocument();
  });

  it('preserves a stale draft on conflict until the user explicitly loads latest', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 2,
      activeVersion: 2,
      revision: 3,
      isActive: true,
      content: {
        title: 'Existing',
        freeFormRules: 'Hold cash when uncertain',
        riskRules: [],
        trackingCriteria: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework
      .mockResolvedValueOnce(existingFramework)
      .mockRejectedValueOnce(
        createApiError(
          createParsedApiError({
            title: '框架加载失败',
            message: '暂时无法读取个人投资框架。',
            rawMessage: 'framework unavailable',
            status: 500,
            category: 'http_error',
            code: 'framework_load_failed',
          }),
        ),
      );
    updateFramework.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '框架版本冲突',
          message: '配置已被其他操作更新。',
          rawMessage: 'revision conflict',
          status: 409,
          category: 'http_error',
          code: 'investment_framework_revision_conflict',
        }),
      ),
    );

    render(<InvestmentFrameworkSettingsCard />);

    await screen.findByDisplayValue('Existing');
    fireEvent.change(screen.getByLabelText('自由规则'), {
      target: { value: 'My pending conflict draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    expect(await screen.findByText('配置已被其他操作更新。')).toBeInTheDocument();
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('自由规则')).toHaveValue('My pending conflict draft');
    expect(screen.getByText(/当前草稿仍被保留/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '载入服务器最新版本' }));
    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('暂时无法读取个人投资框架。')).toBeInTheDocument();
  });

  it('preserves evaluation dimensions the minimal editor does not own', async () => {
    getFramework.mockResolvedValue({
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 1,
      isActive: true,
      content: {
        title: 'Structured',
        freeFormRules: 'Keep free form',
        riskRules: [],
        trackingCriteria: [],
        evaluationDimensions: [
          { name: 'Moat', weight: 50, criteria: ['Durable pricing power'] },
        ],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    });
    updateFramework.mockResolvedValue({
      frameworkId: 1,
      scope: 'local',
      version: 2,
      activeVersion: 2,
      revision: 2,
      isActive: true,
      content: {
        title: 'Structured',
        freeFormRules: 'Keep free form updated',
        riskRules: [],
        trackingCriteria: [],
        evaluationDimensions: [
          { name: 'Moat', weight: 50, criteria: ['Durable pricing power'] },
        ],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T01:00:00Z',
      versionCreatedAt: '2026-07-26T01:00:00Z',
    });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Structured');
    fireEvent.change(screen.getByLabelText('自由规则'), {
      target: { value: 'Keep free form updated' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => {
      expect(updateFramework).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.objectContaining({
            freeFormRules: 'Keep free form updated',
            evaluationDimensions: [
              { name: 'Moat', weight: 50, criteria: ['Durable pricing power'] },
            ],
          }),
        }),
      );
    });
  });

  it('edits and saves a valid decision tree and evaluation dimension', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Structured',
        freeFormRules: 'Keep free form',
        riskRules: [],
        trackingCriteria: [],
        decisionTree: [],
        evaluationDimensions: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework.mockResolvedValue(existingFramework);
    updateFramework.mockResolvedValue({
      ...existingFramework,
      version: 2,
      revision: 8,
    });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Structured');

    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    fireEvent.change(screen.getByLabelText('节点 1 的问题'), {
      target: { value: 'Is quality high?' },
    });
    fireEvent.change(screen.getByLabelText('条件 1'), {
      target: { value: 'Yes' },
    });
    fireEvent.change(screen.getByLabelText('终局'), {
      target: { value: 'Consider' },
    });
    fireEvent.click(screen.getByRole('button', { name: '添加维度' }));
    fireEvent.change(screen.getByLabelText('维度 1 的名称'), {
      target: { value: 'Moat' },
    });
    fireEvent.change(screen.getByLabelText('维度 1 的权重'), {
      target: { value: '60' },
    });
    fireEvent.change(screen.getByLabelText('评估标准（每行一条）'), {
      target: { value: 'Durable pricing power' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => expect(updateFramework).toHaveBeenCalledWith(expect.objectContaining({
      expectedRevision: 7,
      content: expect.objectContaining({
        rootNodeId: 'node-1',
        decisionTree: [
          expect.objectContaining({
            nodeId: 'node-1',
            question: 'Is quality high?',
            branches: [
              expect.objectContaining({ condition: 'Yes', outcome: 'Consider' }),
            ],
          }),
        ],
        evaluationDimensions: [
          expect.objectContaining({
            name: 'Moat',
            weight: 60,
            criteria: ['Durable pricing power'],
          }),
        ],
      }),
    })));
  });

  it('renames a node through an existing ID without retargeting that node references', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Structured',
        rootNodeId: 'A',
        decisionTree: [
          {
            nodeId: 'A',
            question: 'Start?',
            branches: [{ condition: 'Continue', targetNodeId: 'B', outcome: null }],
          },
          {
            nodeId: 'B',
            question: 'Finish?',
            branches: [{ condition: 'Done', targetNodeId: null, outcome: 'Accept' }],
          },
        ],
        evaluationDimensions: [],
        riskRules: [],
        trackingCriteria: [],
        freeFormRules: null,
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework.mockResolvedValue(existingFramework);
    updateFramework.mockResolvedValue({
      ...existingFramework,
      version: 2,
      activeVersion: 2,
      revision: 8,
      content: {
        ...existingFramework.content,
        rootNodeId: 'B2',
        decisionTree: [
          {
            ...existingFramework.content.decisionTree[0],
            nodeId: 'B2',
          },
          existingFramework.content.decisionTree[1],
        ],
      },
    });

    render(<InvestmentFrameworkSettingsCard />);
    const firstNodeId = await screen.findByLabelText('节点 1 的 ID');

    fireEvent.focus(firstNodeId);
    fireEvent.change(firstNodeId, { target: { value: 'B' } });
    fireEvent.change(firstNodeId, { target: { value: 'B2' } });
    fireEvent.blur(firstNodeId);

    expect(screen.getByLabelText('根节点')).toHaveValue('B2');
    expect(within(screen.getByTestId('framework-node-0')).getByLabelText('目标节点'))
      .toHaveValue('B');
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => expect(updateFramework).toHaveBeenCalledWith(expect.objectContaining({
      expectedRevision: 7,
      content: expect.objectContaining({
        rootNodeId: 'B2',
        decisionTree: [
          expect.objectContaining({
            nodeId: 'B2',
            branches: [
              expect.objectContaining({ targetNodeId: 'B' }),
            ],
          }),
          expect.objectContaining({ nodeId: 'B' }),
        ],
      }),
    })));
  });

  it('keeps unrelated graph references when a node rename crosses an existing ID', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Rename safety',
        rootNodeId: 'start',
        decisionTree: [
          {
            nodeId: 'start',
            question: 'Where next?',
            branches: [
              { condition: 'First', targetNodeId: 'A', outcome: null },
              { condition: 'Second', targetNodeId: 'B', outcome: null },
            ],
          },
          {
            nodeId: 'A',
            question: 'A?',
            branches: [{ condition: 'Done', targetNodeId: null, outcome: 'A done' }],
          },
          {
            nodeId: 'B',
            question: 'B?',
            branches: [{ condition: 'Done', targetNodeId: null, outcome: 'B done' }],
          },
        ],
        evaluationDimensions: [],
        riskRules: [],
        trackingCriteria: [],
        freeFormRules: null,
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework.mockResolvedValue(existingFramework);
    updateFramework.mockResolvedValue({
      ...existingFramework,
      version: 2,
      revision: 8,
    });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Rename safety');

    const renamedNodeId = screen.getByLabelText('节点 2 的 ID');
    fireEvent.focus(renamedNodeId);
    fireEvent.change(renamedNodeId, { target: { value: 'C' } });
    fireEvent.change(renamedNodeId, { target: { value: 'B' } });
    fireEvent.change(renamedNodeId, { target: { value: 'B2' } });
    fireEvent.blur(renamedNodeId);
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => expect(updateFramework).toHaveBeenCalledWith(expect.objectContaining({
      expectedRevision: 7,
      content: expect.objectContaining({
        rootNodeId: 'start',
        decisionTree: [
          expect.objectContaining({
            nodeId: 'start',
            branches: [
              expect.objectContaining({ targetNodeId: 'B2' }),
              expect.objectContaining({ targetNodeId: 'B' }),
            ],
          }),
          expect.objectContaining({ nodeId: 'B2' }),
          expect.objectContaining({ nodeId: 'B' }),
        ],
      }),
    })));
  });

  it('blocks Unicode-casefold duplicate dimension names before sending an update', async () => {
    getFramework.mockResolvedValue({
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Structured',
        freeFormRules: null,
        riskRules: [],
        trackingCriteria: [],
        evaluationDimensions: [
          { name: 'Straße', weight: 50, criteria: ['Durability'] },
          { name: 'Quality', weight: 50, criteria: ['Returns'] },
        ],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Straße');
    fireEvent.change(screen.getByLabelText('维度 2 的名称'), {
      target: { value: 'STRASSE' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    expect(updateFramework).not.toHaveBeenCalled();
    const firstDimension = screen.getByTestId('framework-dimension-0');
    const secondDimension = screen.getByTestId('framework-dimension-1');
    expect(firstDimension).toHaveAttribute('data-validation-error', 'true');
    expect(secondDimension).toHaveAttribute('data-validation-error', 'true');
    expect(within(firstDimension).getByRole('alert')).toHaveTextContent(
      '评估维度名称「strasse」重复。',
    );
    expect(within(secondDimension).getByRole('alert')).toHaveTextContent(
      '评估维度名称「strasse」重复。',
    );
  });

  it('submits dimension names that the pinned backend casefold keeps distinct', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Structured',
        freeFormRules: null,
        riskRules: [],
        trackingCriteria: [],
        evaluationDimensions: [
          { name: '\uA7CB', weight: 50, criteria: ['Durability'] },
          { name: '\u0264', weight: 50, criteria: ['Returns'] },
        ],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework.mockResolvedValue(existingFramework);
    updateFramework.mockResolvedValue({
      ...existingFramework,
      version: 2,
      activeVersion: 2,
      revision: 8,
    });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('\uA7CB');
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => expect(updateFramework).toHaveBeenCalledWith(expect.objectContaining({
      expectedRevision: 7,
      content: expect.objectContaining({
        evaluationDimensions: [
          expect.objectContaining({ name: '\uA7CB' }),
          expect.objectContaining({ name: '\u0264' }),
        ],
      }),
    })));
    expect(screen.getByTestId('framework-dimension-0')).not.toHaveAttribute(
      'data-validation-error',
    );
    expect(screen.getByTestId('framework-dimension-1')).not.toHaveAttribute(
      'data-validation-error',
    );
  });

  it('places sanitized 422 issues on the related node and dimension while keeping a global error', async () => {
    const existingFramework = {
      frameworkId: 1,
      scope: 'local',
      version: 1,
      activeVersion: 1,
      revision: 7,
      isActive: true,
      content: {
        title: 'Structured',
        rootNodeId: 'root',
        decisionTree: [
          {
            nodeId: 'root',
            question: 'Start?',
            branches: [{ condition: 'Continue', targetNodeId: 'valuation', outcome: null }],
          },
          {
            nodeId: 'valuation',
            question: 'Value?',
            branches: [{ condition: 'Finish', targetNodeId: null, outcome: 'Done' }],
          },
        ],
        evaluationDimensions: [
          { name: 'Moat', weight: 50, criteria: ['Pricing power'] },
        ],
        riskRules: [],
        trackingCriteria: [],
        freeFormRules: null,
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      versionCreatedAt: '2026-07-26T00:00:00Z',
    };
    getFramework.mockResolvedValue(existingFramework);
    updateFramework.mockRejectedValue(createParsedApiError({
      title: '输入未通过校验',
      message: '检查输入内容后再试。',
      rawMessage: 'Request validation failed',
      status: 422,
      category: 'http_error',
      code: 'validation_error',
      details: {
        issues: [
          {
            type: 'string_too_long',
            loc: ['body', 'content', 'decision_tree', 1, 'question'],
            msg: 'String should have at most 1000 characters',
          },
          {
            type: 'too_long',
            loc: ['body', 'content', 'evaluation_dimensions', 0, 'criteria'],
            msg: 'List should have at most 30 items',
          },
        ],
      },
    }));

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Structured');
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    expect(await screen.findByText('检查输入内容后再试。')).toBeInTheDocument();
    const node = screen.getByTestId('framework-node-1');
    expect(node).toHaveAttribute('data-validation-error', 'true');
    expect(within(node).getByRole('alert')).toHaveTextContent(
      '问题、条件、终局或逐条规则的长度必须为 1–1000 个字符。',
    );
    const dimension = screen.getByTestId('framework-dimension-0');
    expect(dimension).toHaveAttribute('data-validation-error', 'true');
    expect(within(dimension).getByRole('alert')).toHaveTextContent(
      '每个评估维度最多允许 30 条标准。',
    );
    expect(screen.getAllByText('保存前请修正框架结构').length).toBeGreaterThan(0);
  });

  it('inspects immutable history and copies an old version into a current-revision draft', async () => {
    const current = {
      frameworkId: 1,
      scope: 'local',
      version: 3,
      activeVersion: 3,
      revision: 9,
      isActive: true,
      content: {
        title: 'Current rules',
        freeFormRules: 'Current',
        riskRules: [],
        trackingCriteria: [],
      },
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T02:00:00Z',
      versionCreatedAt: '2026-07-26T02:00:00Z',
    };
    getFramework.mockResolvedValue(current);
    historyFramework.mockResolvedValue({
      frameworkId: 1,
      latestVersion: 3,
      activeVersion: 3,
      revision: 9,
      total: 2,
      items: [
        {
          version: 2,
          isActive: false,
          content: {
            title: 'Historical rules',
            freeFormRules: 'Historical',
            riskRules: [],
            trackingCriteria: [],
          },
          changeSummary: 'Older',
          createdAt: '2026-07-26T01:00:00Z',
        },
        {
          version: 3,
          isActive: true,
          content: current.content,
          changeSummary: 'Current',
          createdAt: '2026-07-26T02:00:00Z',
        },
      ],
    });
    updateFramework.mockResolvedValue({ ...current, version: 4, revision: 10 });

    render(<InvestmentFrameworkSettingsCard />);
    await screen.findByDisplayValue('Current rules');
    fireEvent.click(screen.getByRole('button', { name: '版本历史' }));

    expect(await screen.findByText('版本 v3')).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: '版本历史' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText('当前激活')).toBeInTheDocument();
    const historyList = screen.getByRole('list', { name: '框架版本历史' });
    const latestVersionButton = within(historyList).getAllByRole('button')[0];
    expect(latestVersionButton).toHaveAccessibleName('版本 v3');
    expect(within(latestVersionButton).getByText(
      formatDateTime('2026-07-26T02:00:00Z', 'zh'),
    )).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '版本 v2' }));
    const inspector = screen.getByTestId('framework-history-inspector-2');
    expect(within(inspector).getByText('Historical rules')).toBeInTheDocument();
    expect(within(inspector).getByText('只读快照，不提供原地恢复。')).toBeInTheDocument();
    expect(within(inspector).getByText(
      formatDateTime('2026-07-26T01:00:00Z', 'zh'),
    )).toBeInTheDocument();
    expect(within(inspector).getByText('创建时间')).toBeInTheDocument();
    fireEvent.click(within(inspector).getByRole('button', { name: '复制到当前草稿' }));

    expect(screen.getByLabelText('框架名称')).toHaveValue('Historical rules');
    expect(screen.getByLabelText('变更说明（可选）')).toHaveValue('基于历史版本 v2');
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() => expect(updateFramework).toHaveBeenCalledWith(expect.objectContaining({
      expectedRevision: 9,
      content: expect.objectContaining({
        title: 'Historical rules',
        freeFormRules: 'Historical',
      }),
    })));

    fireEvent.click(screen.getByRole('button', { name: '关闭版本历史' }));
    expect(screen.queryByRole('complementary', { name: '版本历史' })).not.toBeInTheDocument();
  });
});
