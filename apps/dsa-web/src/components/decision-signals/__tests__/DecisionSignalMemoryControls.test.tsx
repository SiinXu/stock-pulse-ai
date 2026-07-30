// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { DecisionSignalMemoryFlagItem } from '../../../types/decisionSignals';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { DecisionSignalMemoryControls } from '../DecisionSignalMemoryControls';

const { getMemoryFlag, updateMemoryFlag } = vi.hoisted(() => ({
  getMemoryFlag: vi.fn(),
  updateMemoryFlag: vi.fn(),
}));

vi.mock('../../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    getMemoryFlag,
    updateMemoryFlag,
  },
}));

function memoryFlags(
  signalId: number,
  memorable: boolean,
  ignored: boolean,
): DecisionSignalMemoryFlagItem {
  return {
    signalId,
    memorable,
    ignored,
    createdAt: '2026-07-29T01:00:00Z',
    updatedAt: '2026-07-29T01:01:00Z',
  };
}

function renderControls(signalId = 7) {
  return render(
    <UiLanguageProvider>
      <DecisionSignalMemoryControls signalId={signalId} />
    </UiLanguageProvider>,
  );
}

describe('DecisionSignalMemoryControls', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');
    getMemoryFlag.mockReset();
    updateMemoryFlag.mockReset();
  });

  it('shows an explicit loading state until server flags arrive', async () => {
    let resolveLoad!: (value: DecisionSignalMemoryFlagItem) => void;
    getMemoryFlag.mockImplementationOnce(() => new Promise((resolve) => {
      resolveLoad = resolve;
    }));

    renderControls();

    expect(screen.getByRole('status')).toHaveTextContent('正在加载');
    expect(screen.getByRole('switch', { name: '重点记忆' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: '忽略' })).toBeDisabled();

    await act(async () => {
      resolveLoad(memoryFlags(7, false, false));
      await Promise.resolve();
    });

    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    expect(screen.getByRole('switch', { name: '重点记忆' })).toBeEnabled();
  });

  it.each([
    { memorable: false, ignored: false, badge: '未标记', warning: false },
    { memorable: true, ignored: false, badge: '重点记忆', warning: false },
    { memorable: false, ignored: true, badge: '忽略', warning: false },
    { memorable: true, ignored: true, badge: '重点记忆', warning: true },
  ])(
    'renders memorable=$memorable and ignored=$ignored independently',
    async ({ memorable, ignored, badge, warning }) => {
      getMemoryFlag.mockResolvedValueOnce(memoryFlags(7, memorable, ignored));

      renderControls();

      expect(await screen.findByRole('switch', { name: '重点记忆' }))
        .toHaveAttribute('aria-checked', String(memorable));
      expect(screen.getByRole('switch', { name: '忽略' }))
        .toHaveAttribute('aria-checked', String(ignored));
      expect(screen.getAllByText(badge).length).toBeGreaterThan(0);
      const precedence = screen.queryByText(/“忽略”优先/);
      if (warning) {
        expect(precedence).toBeInTheDocument();
        expect(precedence).toHaveTextContent('仍不会进入历史决策记忆检索');
      } else {
        expect(precedence).not.toBeInTheDocument();
      }
    },
  );

  it('ignores a stale load response after switching signals', async () => {
    let resolveFirst!: (value: DecisionSignalMemoryFlagItem) => void;
    getMemoryFlag
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce(memoryFlags(8, false, true));

    const view = renderControls(7);
    view.rerender(
      <UiLanguageProvider>
        <DecisionSignalMemoryControls signalId={8} />
      </UiLanguageProvider>,
    );

    expect(await screen.findByRole('switch', { name: '忽略' }))
      .toHaveAttribute('aria-checked', 'true');

    await act(async () => {
      resolveFirst(memoryFlags(7, true, false));
      await Promise.resolve();
    });

    expect(screen.getByRole('switch', { name: '重点记忆' }))
      .toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: '忽略' }))
      .toHaveAttribute('aria-checked', 'true');
  });

  it('serializes saves and adopts only the confirmed server response', async () => {
    let resolveSave!: (value: DecisionSignalMemoryFlagItem) => void;
    getMemoryFlag.mockResolvedValueOnce(memoryFlags(7, false, false));
    updateMemoryFlag.mockImplementationOnce(() => new Promise((resolve) => {
      resolveSave = resolve;
    }));

    renderControls();

    const memorableSwitch = await screen.findByRole('switch', { name: '重点记忆' });
    const ignoredSwitch = screen.getByRole('switch', { name: '忽略' });
    await waitFor(() => expect(memorableSwitch).toBeEnabled());
    fireEvent.click(memorableSwitch);
    fireEvent.click(ignoredSwitch);

    expect(updateMemoryFlag).toHaveBeenCalledTimes(1);
    expect(updateMemoryFlag).toHaveBeenCalledWith(7, { memorable: true });
    expect(screen.getByRole('status')).toHaveTextContent('正在保存');
    expect(memorableSwitch).toHaveAttribute('aria-checked', 'false');
    expect(ignoredSwitch).toBeDisabled();

    await act(async () => {
      resolveSave(memoryFlags(7, true, false));
      await Promise.resolve();
    });

    await waitFor(() => expect(memorableSwitch).toHaveAttribute('aria-checked', 'true'));
    expect(ignoredSwitch).toHaveAttribute('aria-checked', 'false');
  });

  it('shows a load failure and retries from server state', async () => {
    getMemoryFlag
      .mockRejectedValueOnce(new Error('network failed'))
      .mockResolvedValueOnce(memoryFlags(7, true, false));

    renderControls();

    expect(await screen.findByText('决策记忆标记加载失败')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: '重点记忆' }))
        .toHaveAttribute('aria-checked', 'true');
    });
    expect(getMemoryFlag).toHaveBeenCalledTimes(2);
  });

  it('retries the failed PATCH payload while keeping confirmed flags unchanged', async () => {
    getMemoryFlag.mockResolvedValueOnce(memoryFlags(7, false, true));
    updateMemoryFlag
      .mockRejectedValueOnce(new Error('save failed'))
      .mockResolvedValueOnce(memoryFlags(7, true, true));

    renderControls();

    const memorableSwitch = await screen.findByRole('switch', { name: '重点记忆' });
    fireEvent.click(memorableSwitch);

    expect(await screen.findByText('决策记忆标记保存失败')).toBeInTheDocument();
    expect(memorableSwitch).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: '忽略' })).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await waitFor(() => expect(updateMemoryFlag).toHaveBeenCalledTimes(2));
    expect(updateMemoryFlag).toHaveBeenNthCalledWith(1, 7, { memorable: true });
    expect(updateMemoryFlag).toHaveBeenNthCalledWith(2, 7, { memorable: true });
    await waitFor(() => expect(memorableSwitch).toHaveAttribute('aria-checked', 'true'));
  });

  it('rejects a response whose signal ID does not match the selected signal', async () => {
    getMemoryFlag.mockResolvedValueOnce(memoryFlags(8, true, true));

    renderControls(7);

    expect(await screen.findByText('决策记忆标记加载失败')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: '重点记忆' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: '忽略' })).toBeDisabled();
    expect(screen.queryByText(/“忽略”优先/)).not.toBeInTheDocument();
  });
});
