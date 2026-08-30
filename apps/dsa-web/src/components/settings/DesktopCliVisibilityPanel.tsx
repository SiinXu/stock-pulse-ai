// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import type { UiLanguage } from '../../i18n/uiText';
import { getDesktopRuntimeApi } from './desktopUpdateModel';
import {
  assertDesktopCliGuidancePathSafe,
  isDesktopCliGuidanceApiAvailable,
  type DesktopCliGuidancePayload,
} from './desktopCliGuidance';

type DesktopCliVisibilityPanelProps = {
  language: UiLanguage;
};

export default function DesktopCliVisibilityPanel({ language }: DesktopCliVisibilityPanelProps) {
  const [payload, setPayload] = useState<DesktopCliGuidancePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => isDesktopCliGuidanceApiAvailable());
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
      const next = await api.getEnvDiagnostics({ locale }) as DesktopCliGuidancePayload;
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
  const title = typeof copy?.title === 'string' ? copy.title.trim() : '';
  const intro = typeof copy?.intro === 'string' ? copy.intro.trim() : '';
  const openTerminalLabel = typeof copy?.openTerminal === 'string' ? copy.openTerminal.trim() : '';
  const openInstallGuideLabel = typeof copy?.openInstallGuide === 'string' ? copy.openInstallGuide.trim() : '';
  const recheckLabel = typeof copy?.recheck === 'string' ? copy.recheck.trim() : '';

  if (!loading && !title && !error) {
    return null;
  }

  const onOpenTerminal = async () => {
    const api = getDesktopRuntimeApi() as
      | (ReturnType<typeof getDesktopRuntimeApi> & {
        openOperatorTerminal?: (payload?: { locale?: string }) => Promise<{ ok?: boolean; message?: string }>;
      })
      | undefined;
    if (!api?.openOperatorTerminal) {
      return;
    }
    const result = await api.openOperatorTerminal({ locale }) as { ok?: boolean; message?: string };
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
    const result = await api.openCliInstallGuide({ command, locale }) as {
      ok?: boolean;
      message?: string;
    };
    setActionMessage(typeof result?.message === 'string' ? result.message : null);
  };

  return (
    <section
      className="space-y-2 rounded-xl border border-border bg-card p-4"
      data-testid="desktop-cli-visibility-panel"
      aria-labelledby="desktop-cli-visibility-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <h3 id="desktop-cli-visibility-heading" className="text-sm font-semibold text-foreground">
            {title || '…'}
          </h3>
          {intro ? (
            <p className="text-xs text-secondary-text">
              {intro}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {openTerminalLabel ? (
            <button
              type="button"
              className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
              onClick={() => void onOpenTerminal()}
              data-testid="desktop-cli-open-terminal"
            >
              {openTerminalLabel}
            </button>
          ) : null}
          {recheckLabel ? (
            <button
              type="button"
              className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
              onClick={() => void refresh()}
              disabled={loading}
              data-testid="desktop-cli-recheck"
            >
              {recheckLabel}
            </button>
          ) : null}
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
                {command.installGuideAvailable && command.status !== 'available' && openInstallGuideLabel ? (
                  <button
                    type="button"
                    className="settings-accent-text inline-flex min-h-11 min-w-11 items-center underline-offset-2 hover:underline"
                    onClick={() => void onOpenGuide(command.name)}
                    data-testid={`desktop-cli-install-${command.name}`}
                  >
                    {openInstallGuideLabel}
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
