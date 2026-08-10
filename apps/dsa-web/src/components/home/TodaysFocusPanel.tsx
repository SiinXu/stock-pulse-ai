// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Focus, RefreshCw } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type { UiTextKey } from '../../i18n/uiText';
import {
  buildAnalysisWorkbenchHref,
  buildSignalCenterHref,
} from '../../routing/routes';
import type { TodaysFocusItem, TodaysFocusResponse } from '../../types/todaysFocus';
import {
  ApiErrorAlert,
  Badge,
  Button,
  EmptyState,
  IconButton,
  Spinner,
  Surface,
} from '../common';

export type TodaysFocusPanelProps = {
  data: TodaysFocusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  onRefresh: () => void;
  onSelectSymbol?: (code: string) => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function reasonBadgeLabel(reasonCode: string, t: TodaysFocusPanelProps['t']): string {
  switch (reasonCode) {
    case 'alert_triggered':
      return t('home.todaysFocus.reason.alert');
    case 'corporate_event':
      return t('home.todaysFocus.reason.event');
    case 'analysis_reversal':
      return t('home.todaysFocus.reason.reversal');
    default:
      return reasonCode;
  }
}

function evidenceHref(item: TodaysFocusItem): string | null {
  switch (item.evidence.type) {
    case 'alert':
      return buildSignalCenterHref({
        triggerId: item.evidence.triggerId,
        stock: item.code,
      });
    case 'analysis':
      return buildAnalysisWorkbenchHref({
        recordId: item.evidence.recordId,
        stock: item.code,
      });
    case 'corporate_event':
      return item.evidence.href.startsWith('/') && !item.evidence.href.startsWith('//')
        ? item.evidence.href
        : null;
    default:
      return null;
  }
}

function FocusRow({
  item,
  onSelect,
  t,
}: {
  item: TodaysFocusItem;
  onSelect?: (code: string) => void;
  t: TodaysFocusPanelProps['t'];
}) {
  const href = evidenceHref(item);
  const content = (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground" data-testid="todays-focus-code">
            {item.code}
          </span>
          {item.name && item.name !== item.code ? (
            <span className="truncate text-xs text-secondary-text">{item.name}</span>
          ) : null}
          <Badge variant="info" data-testid="todays-focus-reason-badge">
            {reasonBadgeLabel(item.reasonCode, t)}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-secondary-text" data-testid="todays-focus-reason">
          {item.reasonDisplay}
        </p>
      </div>
      {typeof item.weightPct === 'number' ? (
        <span className="shrink-0 text-xs tabular-nums text-secondary-text">
          {t('home.todaysFocus.weight', { value: item.weightPct.toFixed(1) })}
        </span>
      ) : null}
    </>
  );

  return (
    <li className="flex items-start gap-3 border-b border-border/60 last:border-b-0">
      {onSelect ? (
        <button
          type="button"
          className="flex min-h-12 min-w-0 flex-1 items-start gap-3 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => onSelect(item.code)}
          data-testid={`todays-focus-item-${item.code}`}
          data-reason-code={item.reasonCode}
        >
          {content}
        </button>
      ) : (
        <div
          className="flex min-h-12 min-w-0 flex-1 items-start gap-3 py-3"
          data-testid={`todays-focus-item-${item.code}`}
          data-reason-code={item.reasonCode}
        >
          {content}
        </div>
      )}
      {href ? (
        <a
          href={href}
          className="my-3 shrink-0 rounded-sm text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${t('home.todaysFocus.viewEvidence')}: ${item.code}`}
          data-testid={`todays-focus-evidence-${item.code}`}
        >
          {t('home.todaysFocus.viewEvidence')}
        </a>
      ) : null}
    </li>
  );
}

/** Self-contained Today's Focus panel (T26). Home wiring is an Integration Point. */
export const TodaysFocusPanel: React.FC<TodaysFocusPanelProps> = ({
  data,
  isLoading,
  error,
  onRefresh,
  onSelectSymbol,
  t,
}) => {
  const items = data?.items ?? [];
  const isEmpty = !isLoading && !error && (data?.status === 'empty' || items.length === 0);

  return (
    <Surface
      as="section"
      level="interactive"
      padding="md"
      aria-labelledby="todays-focus-heading"
      data-testid="todays-focus-panel"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Focus className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <h2 id="todays-focus-heading" className="text-base font-semibold text-foreground">
              {t('home.todaysFocus.title')}
            </h2>
          </div>
          <p className="mt-1 text-xs text-secondary-text">{t('home.todaysFocus.subtitle')}</p>
        </div>
        <IconButton
          type="button"
          variant="ghost"
          size="compact"
          aria-label={t('home.todaysFocus.refresh')}
          onClick={onRefresh}
          disabled={isLoading}
          data-testid="todays-focus-refresh"
        >
          {isLoading ? <Spinner className="h-4 w-4" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
        </IconButton>
      </div>

      {error ? (
        <div className="space-y-3" data-testid="todays-focus-error">
          <ApiErrorAlert error={error} />
          <Button type="button" variant="secondary" size="compact" onClick={onRefresh}>
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {isLoading && !data ? (
        <div className="flex min-h-24 items-center justify-center gap-2 text-sm text-secondary-text" data-testid="todays-focus-loading">
          <Spinner className="h-4 w-4" aria-hidden="true" />
          {t('home.todaysFocus.loading')}
        </div>
      ) : null}

      {!error && data?.status === 'degraded' ? (
        <p
          className="mb-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-secondary-text"
          role="status"
          data-testid="todays-focus-degraded"
        >
          {t('home.todaysFocus.degraded')}
        </p>
      ) : null}

      {isEmpty ? (
        <EmptyState
          title={t('home.todaysFocus.emptyTitle')}
          description={t('home.todaysFocus.emptyDescription')}
          data-testid="todays-focus-empty"
        />
      ) : null}

      {!error && items.length > 0 ? (
        <ul className="list-none p-0" data-testid="todays-focus-list" aria-label={t('home.todaysFocus.listLabel')}>
          {items.map((item) => (
            <FocusRow key={item.code} item={item} onSelect={onSelectSymbol} t={t} />
          ))}
        </ul>
      ) : null}

      {!error && data && items.length > 0 ? (
        <p className="mt-3 text-xs text-secondary-text" data-testid="todays-focus-cap-hint">
          {t('home.todaysFocus.capHint', { count: data.itemCount, max: data.maxItems })}
        </p>
      ) : null}
    </Surface>
  );
};

export default TodaysFocusPanel;
