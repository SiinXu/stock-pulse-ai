// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { KronosStatusPanel } from '../KronosStatusPanel';

const getKronosStatus = vi.fn();

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getKronosStatus: (...args: unknown[]) => getKronosStatus(...args),
  },
}));

vi.mock('../../../contexts/UiLanguageContext', () => ({
  useUiLanguage: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (params?.size) return `${key}:${params.size}`;
      if (params?.time) return `${key}:${params.time}`;
      return key;
    },
    language: 'en',
  }),
}));

describe('KronosStatusPanel', () => {
  beforeEach(() => {
    getKronosStatus.mockReset();
  });

  it('renders status badges, next step, and refresh action', async () => {
    getKronosStatus.mockResolvedValue({
      enabled: false,
      modelSize: 'mini',
      ready: false,
      reason: 'disabled',
      message: 'Kronos agent tool is disabled.',
      nextStep: 'Install optional deps then enable.',
      dependenciesInstalled: false,
      dependencies: [
        { name: 'torch', available: false },
        { name: 'huggingface_hub', available: false },
      ],
      weightsPresent: false,
      weightsTotalBytes: null,
      weightsModifiedAt: null,
      packagedDesktop: false,
      installSupported: true,
      downloadSizeHint: '~40 MB (Kronos-mini + Kronos-Tokenizer-2k)',
    });

    render(<KronosStatusPanel />);

    await waitFor(() => {
      expect(screen.getByText('settings.kronosNeedsAction')).toBeInTheDocument();
    });
    expect(screen.getByText('settings.kronosDisabledLabel')).toBeInTheDocument();
    expect(screen.getByText('Kronos agent tool is disabled.')).toBeInTheDocument();
    expect(screen.getByText('Install optional deps then enable.')).toBeInTheDocument();
    expect(screen.getByText('settings.kronosDocHint')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /settings.kronosStatusRefresh/i }));
    await waitFor(() => {
      expect(getKronosStatus).toHaveBeenCalledTimes(2);
    });
  });

  it('shows desktop unsupported copy when install is not supported', async () => {
    getKronosStatus.mockResolvedValue({
      enabled: true,
      modelSize: 'mini',
      ready: false,
      reason: 'packaged_desktop_unsupported',
      message: 'Ready but desktop blocked.',
      nextStep: 'Use a source install.',
      dependenciesInstalled: true,
      dependencies: [{ name: 'torch', available: true }],
      weightsPresent: true,
      weightsTotalBytes: 1024,
      weightsModifiedAt: '2026-08-05T00:00:00+00:00',
      packagedDesktop: true,
      installSupported: false,
      downloadSizeHint: null,
    });

    render(<KronosStatusPanel />);

    await waitFor(() => {
      expect(screen.getByText('settings.kronosDesktopUnsupported')).toBeInTheDocument();
    });
  });
});
