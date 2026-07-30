// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { SystemConfigConflictError } from '../../../api/systemConfig';
import SystemConfigRollbackCard from '../SystemConfigRollbackCard';

const rollback = vi.hoisted(() => vi.fn());

vi.mock('../../../api/systemConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/systemConfig')>();
  return {
    ...actual,
    systemConfigApi: {
      ...actual.systemConfigApi,
      rollback,
    },
  };
});

const rollbackResult = {
  success: true,
  configVersion: 'v2',
  appliedCount: 3,
  skippedMaskedCount: 0,
  reloadTriggered: true,
  updatedKeys: ['SCHEDULE_TIME'],
  warnings: [],
};

describe('SystemConfigRollbackCard', () => {
  beforeEach(() => {
    rollback.mockReset();
  });

  it('confirms against the visible current version and refreshes after success', async () => {
    const onRolledBack = vi.fn().mockResolvedValue(undefined);
    rollback.mockResolvedValue(rollbackResult);

    render(
      <SystemConfigRollbackCard
        configVersion="v3"
        onRolledBack={onRolledBack}
        onReloadLatest={vi.fn()}
      />,
    );

    expect(screen.getByText('当前配置版本：v3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '回滚配置' }));
    expect(screen.getByRole('dialog', { name: '确认回滚系统配置？' })).toHaveTextContent('v3');
    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }));

    await waitFor(() => expect(rollback).toHaveBeenCalledWith({ configVersion: 'v3' }));
    await waitFor(() => expect(onRolledBack).toHaveBeenCalledWith(rollbackResult));
    expect(await screen.findByText('配置已回滚并重新载入最新状态。')).toBeInTheDocument();
  });

  it('does not retry a conflict and offers an explicit latest-state reload', async () => {
    const onReloadLatest = vi.fn().mockResolvedValue(undefined);
    rollback.mockRejectedValue(new SystemConfigConflictError(
      '配置已由其他操作更新。',
      'v4',
      createParsedApiError({
        title: '配置版本冲突',
        message: '配置已由其他操作更新。',
        rawMessage: 'conflict',
        status: 409,
        category: 'http_error',
        code: 'config_version_conflict',
      }),
    ));

    render(
      <SystemConfigRollbackCard
        configVersion="v3"
        onRolledBack={vi.fn()}
        onReloadLatest={onReloadLatest}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '回滚配置' }));
    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }));

    expect(await screen.findByText('服务器配置已更新，请刷新后重新应用本次修改。')).toBeInTheDocument();
    expect(rollback).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '载入最新配置' }));
    await waitFor(() => expect(onReloadLatest).toHaveBeenCalledTimes(1));
    expect(rollback).toHaveBeenCalledTimes(1);
  });

  it('reports a committed rollback separately when the page refresh fails', async () => {
    rollback.mockResolvedValue(rollbackResult);

    render(
      <SystemConfigRollbackCard
        configVersion="v3"
        onRolledBack={vi.fn().mockRejectedValue(new Error('offline'))}
        onReloadLatest={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '回滚配置' }));
    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }));

    expect(await screen.findByText('回滚已提交，但页面刷新失败')).toBeInTheDocument();
    expect(screen.getByText(/服务器已完成回滚/)).toBeInTheDocument();
  });

  it('does not offer a reload action when no rollback snapshot exists', async () => {
    rollback.mockRejectedValue(createParsedApiError({
      title: '没有可回滚的配置',
      message: '当前没有可用的上一份稳定配置，未执行任何更改。',
      rawMessage: 'rollback_unavailable',
      status: 409,
      category: 'http_error',
      code: 'rollback_unavailable',
    }));

    render(
      <SystemConfigRollbackCard
        configVersion="v3"
        onRolledBack={vi.fn()}
        onReloadLatest={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '回滚配置' }));
    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }));

    expect(await screen.findByText('没有可回滚的配置')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '载入最新配置' })).not.toBeInTheDocument();
  });
});
