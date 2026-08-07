// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ArrowRight, RefreshCw, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { ParsedApiError } from '../../api/error';
import type { SetupStatusCheck, SetupStatusResponse } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import {
  ApiErrorAlert,
  Button,
  IconButton,
  StatePanel,
  StatusDot,
  Surface,
} from '../common';
import {
  orderSetupChecksForHome,
  resolveSetupCheckActionLabel,
  resolveSetupCheckHref,
  resolveSetupCheckLabel,
  resolveSetupCheckStatusLabel,
  resolveSetupCheckTone,
} from './setupStatusPresentation';

export type HomeReadinessCardProps = {
  status: SetupStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  /** Optional client-side last-success signal (recent analysis available). */
  lastSuccess?: {
    ok: boolean;
    href: string;
    detail?: string;
  } | null;
  onRefresh: () => void;
  onDismiss?: () => void;
  dismissible?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function CheckRow({
  check,
  onFix,
  t,
}: {
  check: SetupStatusCheck;
  onFix: (href: string) => void;
  t: HomeReadinessCardProps['t'];
}) {
  const tone = resolveSetupCheckTone(check);
  const needsAction = check.status === 'needs_action';
  const label = resolveSetupCheckLabel(check, t, { goalLanguage: true });
  const statusLabel = resolveSetupCheckStatusLabel(check, t);

  return (
    <li
      className="flex min-h-12 items-center gap-3 border-b border-border/60 py-2 last:border-b-0"
      data-testid={`home-readiness-check-${check.key}`}
      data-status={check.status}
      data-tone={tone}
    >
      <StatusDot tone={tone} aria-label={statusLabel} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{label}</p>
        <p className="mt-0.5 truncate text-xs text-secondary-text">
          {needsAction && check.nextStep ? check.nextStep : check.message}
        </p>
      </div>
      {needsAction ? (
        <Button
          type="button"
          variant="secondary"
          size="compact"
          className="shrink-0"
          onClick={() => onFix(resolveSetupCheckHref(check))}
        >
          {resolveSetupCheckActionLabel(check, t)}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      ) : null}
    </li>
  );
}

export const HomeReadinessCard: React.FC<HomeReadinessCardProps> = ({
  status,
  isLoading,
  error,
  lastSuccess = null,
  onRefresh,
  onDismiss,
  dismissible = false,
  t,
}) => {
  const navigate = useNavigate();
  const checks = status ? orderSetupChecksForHome(status.checks) : [];
  const gapCount = checks.filter((check) => check.status === 'needs_action').length;
  const isComplete = Boolean(status?.isComplete) && gapCount === 0;

  const summaryTitle = !status
    ? error
      ? t('home.readiness.errorTitle')
      : t('home.readiness.loadingTitle')
    : isComplete
      ? t('home.readiness.readyTitle')
      : t('home.readiness.gapTitle', { count: gapCount });

  const summaryMessage = !status
    ? error
      ? t('home.readiness.errorMessage')
      : t('home.readiness.loadingMessage')
    : isComplete
      ? t('home.readiness.readyMessage')
      : t('home.readiness.gapMessage');

  return (
    <Surface
      level="interactive"
      padding="md"
      className="space-y-3"
      data-testid="home-readiness-card"
      aria-labelledby="home-readiness-heading"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusDot
              tone={
                !status
                  ? error
                    ? 'danger'
                    : 'neutral'
                  : isComplete
                    ? 'success'
                    : gapCount > 0
                      ? 'warning'
                      : 'success'
              }
              pulse={isLoading && !status}
              aria-label={summaryTitle}
            />
            <h2
              id="home-readiness-heading"
              className="text-sm font-semibold text-foreground"
            >
              {t('home.readiness.title')}
            </h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-secondary-text">
            <span className="font-medium text-foreground">{summaryTitle}</span>
            {' · '}
            {summaryMessage}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            type="button"
            variant="ghost"
            size="default"
            aria-label={t('home.readiness.refresh')}
            isLoading={isLoading}
            onClick={onRefresh}
          >
            <RefreshCw aria-hidden="true" />
          </IconButton>
          {dismissible && onDismiss ? (
            <IconButton
              type="button"
              variant="ghost"
              size="default"
              aria-label={t('common.close')}
              onClick={onDismiss}
            >
              <X aria-hidden="true" />
            </IconButton>
          ) : null}
        </div>
      </div>

      {error ? (
        <ApiErrorAlert
          error={error}
          actionLabel={t('common.retry')}
          onAction={onRefresh}
        />
      ) : null}

      {isLoading && !status ? (
        <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
      ) : null}

      {!isLoading && !error && status && checks.length === 0 ? (
        <StatePanel
          state="empty"
          title={t('home.readiness.emptyTitle')}
          description={t('home.readiness.emptyMessage')}
          size="compact"
          titleAs="p"
        />
      ) : null}

      {status && checks.length > 0 ? (
        <ul className="m-0 list-none p-0" data-testid="home-readiness-checks">
          {checks.map((check) => (
            <CheckRow
              key={check.key}
              check={check}
              onFix={(href) => navigate(href)}
              t={t}
            />
          ))}
          {lastSuccess ? (
            <li
              className="flex min-h-12 items-center gap-3 border-b border-border/60 py-2 last:border-b-0"
              data-testid="home-readiness-check-last_success"
              data-status={lastSuccess.ok ? 'configured' : 'needs_action'}
              data-tone={lastSuccess.ok ? 'success' : 'warning'}
            >
              <StatusDot
                tone={lastSuccess.ok ? 'success' : 'warning'}
                aria-label={
                  lastSuccess.ok
                    ? t('home.readiness.lastSuccess.ok')
                    : t('home.readiness.lastSuccess.missing')
                }
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {t('home.readiness.goal.last_success')}
                </p>
                <p className="mt-0.5 truncate text-xs text-secondary-text">
                  {lastSuccess.detail
                    || (lastSuccess.ok
                      ? t('home.readiness.lastSuccess.ok')
                      : t('home.readiness.lastSuccess.missing'))}
                </p>
              </div>
              {!lastSuccess.ok ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="compact"
                  className="shrink-0"
                  onClick={() => navigate(lastSuccess.href)}
                >
                  {t('home.readiness.action.last_success')}
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              ) : null}
            </li>
          ) : null}
        </ul>
      ) : null}
    </Surface>
  );
};

export default HomeReadinessCard;
