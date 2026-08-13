// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { assertDesktopCliGuidancePathSafe } from '../desktopCliGuidance';
import DesktopCliVisibilityPanel from '../DesktopCliVisibilityPanel';

describe('DesktopCliVisibilityPanel', () => {
  beforeEach(() => {
    delete (window as { dsaDesktop?: unknown }).dsaDesktop;
  });

  it('renders nothing outside Desktop', () => {
    const { container } = render(<DesktopCliVisibilityPanel language="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders path-safe guidance and actionable controls on Desktop', async () => {
    const getEnvDiagnostics = vi.fn(async () => ({
      schemaVersion: 2,
      copy: {
        title: 'CLI visibility for the Desktop process',
        intro: 'Bounded probe.',
        openTerminal: 'Open system terminal',
        openInstallGuide: 'Open install guide',
        recheck: 'Recheck',
        pathUnavailable: null,
      },
      commands: [
        {
          name: 'codex',
          status: 'missing' as const,
          reason: null,
          statusLabel: 'Missing',
          hint: 'Install on login PATH.',
          installGuideAvailable: true,
        },
      ],
      needsAction: true,
    }));
    const openOperatorTerminal = vi.fn(async () => ({ ok: true, message: 'Tried to open the system terminal.' }));
    const openCliInstallGuide = vi.fn(async () => ({ ok: true, message: 'Opened the install guide in the system browser.' }));

    Object.defineProperty(window, 'dsaDesktop', {
      configurable: true,
      value: {
        version: '3.12.0',
        getEnvDiagnostics,
        openOperatorTerminal,
        openCliInstallGuide,
      },
    });

    render(<DesktopCliVisibilityPanel language="en" />);
    await waitFor(() => {
      expect(screen.getByTestId('desktop-cli-visibility-panel')).toBeInTheDocument();
    });
    expect(screen.getByTestId('desktop-cli-row-codex')).toHaveAttribute('data-status', 'missing');
    expect(screen.queryByText(/\/opt\/homebrew/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/Users\//)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('desktop-cli-open-terminal'));
    await waitFor(() => {
      expect(openOperatorTerminal).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByTestId('desktop-cli-install-codex'));
    await waitFor(() => {
      expect(openCliInstallGuide).toHaveBeenCalledWith({ command: 'codex', locale: 'en' });
    });
  });

  it('rejects payloads that leak filesystem path tokens', () => {
    expect(() => assertDesktopCliGuidancePathSafe({
      copy: { intro: '/Users/secret/bin' },
    })).toThrow(/leaked/);
  });
});
