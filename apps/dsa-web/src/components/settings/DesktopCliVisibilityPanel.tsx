// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import type { UiLanguage } from '../../i18n/uiText';
import { getDesktopRuntimeApi } from './desktopUpdateModel';

export type DesktopCliCommandGuidance = {
  name: string;
  status: 'available' | 'missing' | 'unknown';
  reason: string | null;
  statusLabel: string;
  hint: string;
  installGuideAvailable: boolean;
};

export type DesktopCliGuidancePayload = {
  schemaVersion?: number;
  generatedAt?: string | null;
  platform?: string;
  path?: {
    effectiveEntryCount?: number;
    limited?: boolean;
    augmented?: boolean;
    policy?: string;
  };
  copy?: {
    title?: string;
    intro?: string;
    openTerminal?: string;
    openInstallGuide?: string;
    recheck?: string;
    pathUnavailable?: string | null;
  };
  needsAction?: boolean;
  commands?: DesktopCliCommandGuidance[];
};

function isDesktopCliGuidanceApiAvailable() {
  const api = getDesktopRuntimeApi() as
    | (ReturnType<typeof getDesktopRuntimeApi> & {
      getEnvDiagnostics?: (payload?: { locale?: string }) => Promise<DesktopCliGuidancePayload>;
      openOperatorTerminal?: (payload?: { locale?: string }) => Promise<{ ok?: boolean; message?: string }>;
      openCliInstallGuide?: (payload?: {
        command?: string;
        locale?: string;
      }) => Promise<{ ok?: boolean; message?: string; urlHost?: string }>;
    })
    | undefined;
  return Boolean(api && typeof api.getEnvDiagnostics === 'function');
}

function containsForbiddenPathToken(value: string) {
  return /\/opt\/homebrew|\/usr\/local\/bin|\/Users\/|C:\\|C:\/|Application Support|PATHEXT/i.test(value);
}

export function assertDesktopCliGuidancePathSafe(payload: DesktopCliGuidancePayload | null | undefined) {
  if (!payload) {
    return;
  }
  const serialized = JSON.stringify(payload);
  if (containsForbiddenPathToken(serialized)) {
    throw new Error('Desktop CLI guidance payload leaked a filesystem path token');
  }
}

type DesktopCliVisibilityPanelProps = {
  language: UiLanguage;
};

export function DesktopCliVisibilityPanel({ language }: DesktopCliVisibilityPanelProps) {
  const [payload, setPayload] = useState<DesktopCliGuidancePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const locale = language === 'zh' ? 'zh' : 'en';

  const refresh = useCallback(async () => {
    const api = getDesktopRuntimeApi() as
      | (ReturnType<typeof getDesktopRuntimeApi> & {
        getEnvDiagnostics?: (payload?: { locale?: string }) => Promise<DesktopCliGuidancePayload>;
      })
      | undefined;
    if (!api || typeof api.getEnvDiagnostics !== 'function') {
      setPayload(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const next = await api.getEnvDiagnostics({ locale });
      assertDesktopCliGuidancePathSafe(next);
      setPayload(next);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : String(refreshError));
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [locale]);

  useEffect(() => {
    if (!isDesktopCliGuidanceApiAvailable()) {
      return undefined;
    }
    void refresh();
    return undefined;
  }, [refresh]);

  if (!isDesktopCliGuidanceApiAvailable()) {
    return null;
  }

  const copy = payload?.copy;
  const commands = Array.isArray(payload?.commands) ? payload.commands : [];

  const onOpenTerminal = async () => {
    const api = getDesktopRuntimeApi() as
      | (ReturnType<typeof getDesktopRuntimeApi> & {
        openOperatorTerminal?: (payload?: { locale?: string }) => Promise<{ ok?: boolean; message?: string }>;
      })
      | undefined;
    if (!api?.openOperatorTerminal) {
      return;
    }
    const result = await api.openOperatorTerminal({ locale });
    setActionMessage(typeof result?.message === 'string' ? result.message : null);
  };

  const onOpenGuide = async (command: string) => {
    const api = getDesktopRuntimeApi() as
      | (ReturnType<typeof getDesktopRuntimeApi> & {
        openCliInstallGuide?: (payload?: {
          command?: string;
          locale?: string;
        }) => Promise<{ ok?: boolean; message?: string }>;
      })
      | undefined;
    if (!api?.openCliInstallGuide) {
      return;
    }
    const result = await api.openCliInstallGuide({ command, locale });
    setActionMessage(typeof result?.message === 'string' ? result.message : null);
  };

  return (
    <section
      className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
      data-testid="desktop-cli-visibility-panel"
      aria-labelledby="desktop-cli-visibility-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <h3 id="desktop-cli-visibility-heading" className="text-sm font-semibold text-foreground">
            {copy?.title || (language === 'zh' ? '本机 CLI 可见性' : 'Local CLI visibility')}
          </h3>
          <p className="text-xs text-secondary-text">
            {copy?.intro || ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
            onClick={() => void onOpenTerminal()}
            data-testid="desktop-cli-open-terminal"
          >
            {copy?.openTerminal || (language === 'zh' ? '打开系统终端' : 'Open system terminal')}
          </button>
          <button
            type="button"
            className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
            onClick={() => void refresh()}
            disabled={loading}
            data-testid="desktop-cli-recheck"
          >
            {copy?.recheck || (language === 'zh' ? '重新检测' : 'Recheck')}
          </button>
        </div>
      </div>
      {copy?.pathUnavailable ? (
        <p className="text-xs text-warning" data-testid="desktop-cli-path-unavailable">
          {copy.pathUnavailable}
        </p>
      ) : null}
      {error ? (
        <p className="text-xs text-danger" data-testid="desktop-cli-visibility-error">{error}</p>
      ) : null}
      {actionMessage ? (
        <p className="text-xs text-secondary-text" data-testid="desktop-cli-action-message">{actionMessage}</p>
      ) : null}
      {loading && !commands.length ? (
        <p className="text-xs text-muted-text" data-testid="desktop-cli-visibility-loading">…</p>
      ) : (
        <ul className="space-y-2" data-testid="desktop-cli-visibility-list">
          {commands.map((command) => (
            <li
              key={command.name}
              className="space-y-1 text-xs text-secondary-text"
              data-testid={`desktop-cli-row-${command.name}`}
              data-status={command.status}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-foreground">
                  {command.name}
                  {' · '}
                  {command.statusLabel}
                </span>
                {command.installGuideAvailable && command.status !== 'available' ? (
                  <button
                    type="button"
                    className="settings-accent-text inline-flex min-h-11 min-w-11 items-center underline-offset-2 hover:underline"
                    onClick={() => void onOpenGuide(command.name)}
                    data-testid={`desktop-cli-install-${command.name}`}
                  >
                    {copy?.openInstallGuide || (language === 'zh' ? '打开安装说明' : 'Open install guide')}
                  </button>
                ) : null}
              </div>
              <p>{command.hint}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export { isDesktopCliGuidanceApiAvailable };
