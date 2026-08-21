// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import ConfigBackupCard from '../ConfigBackupCard';

const { importEnv, exportEnv, useAuthMock } = vi.hoisted(() => ({
  importEnv: vi.fn(),
  exportEnv: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../../../hooks', () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock('../../../api/systemConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/systemConfig')>();
  return {
    ...actual,
    systemConfigApi: {
      ...actual.systemConfigApi,
      importEnv,
      exportEnv,
    },
  };
});

describe('ConfigBackupCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthMock.mockReturnValue({ authEnabled: true });
    importEnv.mockReset();
    exportEnv.mockReset();
  });

  it('offers reload recovery for a 409 env-import conflict', async () => {
    const load = vi.fn().mockResolvedValue(true);
    importEnv.mockRejectedValue(createApiError(createParsedApiError({
      title: '配置版本冲突',
      message: '配置已由其他操作更新。',
      rawMessage: 'conflict',
      status: 409,
      category: 'http_error',
      code: 'config_version_conflict',
    })));

    render(
      <ConfigBackupCard
        configVersion="v1"
        hasDirty={false}
        disabled={false}
        load={load}
        onSchedulerKeysImported={vi.fn()}
        onRefreshSetupStatus={vi.fn()}
        onRolledBack={vi.fn()}
        onReloadLatest={vi.fn()}
      />,
    );

    const input = document.querySelector('input[type="file"][accept=".env,.txt"]');
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'backup.env', { type: 'text/plain' })],
      },
    });

    const reload = await screen.findByRole('button', { name: '重新加载' });
    expect(screen.getByRole('button', { name: '导入 .env' })).toBeEnabled();
    fireEvent.click(reload);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  });

  it('does not offer reload recovery for a non-conflict env-import failure', async () => {
    importEnv.mockRejectedValue(createApiError(createParsedApiError({
      title: '导入失败',
      message: '备份无法读取。',
      rawMessage: 'import failed',
      status: 500,
      category: 'http_error',
      code: 'internal_error',
    })));

    render(
      <ConfigBackupCard
        configVersion="v1"
        hasDirty={false}
        disabled={false}
        load={vi.fn()}
        onSchedulerKeysImported={vi.fn()}
        onRefreshSetupStatus={vi.fn()}
        onRolledBack={vi.fn()}
        onReloadLatest={vi.fn()}
      />,
    );

    const input = document.querySelector('input[type="file"][accept=".env,.txt"]');
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'backup.env', { type: 'text/plain' })],
      },
    });

    expect(await screen.findByText('导入失败')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新加载' })).not.toBeInTheDocument();
  });
});
