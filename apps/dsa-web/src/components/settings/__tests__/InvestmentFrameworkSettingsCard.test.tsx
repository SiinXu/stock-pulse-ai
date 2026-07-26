// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { InvestmentFrameworkSettingsCard } from '../InvestmentFrameworkSettingsCard';

const { getFramework, createFramework, updateFramework, deactivateFramework, removeFramework } = vi.hoisted(() => ({
  getFramework: vi.fn(),
  createFramework: vi.fn(),
  updateFramework: vi.fn(),
  deactivateFramework: vi.fn(),
  removeFramework: vi.fn(),
}));

vi.mock('../../../api/investmentFramework', () => ({
  investmentFrameworkApi: {
    get: getFramework,
    create: createFramework,
    update: updateFramework,
    deactivate: deactivateFramework,
    remove: removeFramework,
  },
}));

describe('InvestmentFrameworkSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    updateFramework.mockResolvedValue({
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
    });

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
    expect(await screen.findByText('已保存为新版本并激活')).toBeInTheDocument();
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
});
