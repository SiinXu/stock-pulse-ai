// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Focus, RefreshCw } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type { UiTextKey } from '../../i18n/uiText';
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
    case 'high_weight_move':
      return t('home.todaysFocus.reason.weightMove');
    default:
      return reasonCode;
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

  if (onSelect) {
    return (
      <li className="border-b border-border/60 last:border-b-0">
        <button
          type="button"
          className="flex w-full min-h-12 items-start gap-3 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => onSelect(item.code)}
          data-testid={`todays-focus-item-${item.code}`}
          data-reason-code={item.reasonCode}
        >
          {content}
        </button>
      </li>
    );
  }

  return (
    <li
      className="flex min-h-12 items-start gap-3 border-b border-border/60 py-3 last:border-b-0"
      data-testid={`todays-focus-item-${item.code}`}
      data-reason-code={item.reasonCode}
    >
      {content}
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
    <Surface className="p-4" data-testid="todays-focus-panel">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Focus className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <h2 className="text-base font-semibold text-foreground">{t('home.todaysFocus.title')}</h2>
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
        <p className="mt-3 text-[11px] text-secondary-text" data-testid="todays-focus-cap-hint">
          {t('home.todaysFocus.capHint', { count: data.itemCount, max: data.maxItems })}
        </p>
      ) : null}
    </Surface>
  );
};

export default TodaysFocusPanel;
