// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Badge, Card, InlineAlert } from '../common';
import type { EventAlertDisplayItem } from '../../types/eventAlerts';
import { isCorporateEventCategory } from '../../utils/eventAlertContext';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVENT_ALERT_PAGE_TEXT, EVENT_CATEGORY_LABELS } from '../../locales/eventAlerts';
import { formatUiNumber, formatUiDateTime } from '../../utils/uiLocale';
import { formatUiText } from '../../i18n/uiText';

export interface EventAlertDetailProps { item?: EventAlertDisplayItem | null; }

const EventAlertDetail: React.FC<EventAlertDetailProps> = ({ item = null }) => {
  const { language } = useUiLanguage();
  const text = EVENT_ALERT_PAGE_TEXT[language];
  const categoryLabels = EVENT_CATEGORY_LABELS[language];
  if (!item) {
    return (
      <Card title={text.detailTitle} level="interactive" padding="md">
        <p className="text-sm text-secondary-text" data-testid="event-alert-detail-empty">{text.selectPrompt}</p>
      </Card>
    );
  }
  const categoryLabel = isCorporateEventCategory(item.eventCategory) ? categoryLabels[item.eventCategory] : (item.eventCategory || '--');
  const bits: string[] = [];
  if (item.inPortfolio) {
    bits.push(item.weightPct != null
      ? formatUiText(text.weight, { value: formatUiNumber(item.weightPct, language, { maximumFractionDigits: 1 }) })
      : text.inPortfolio);
  }
  if (item.inWatchlist) bits.push(text.inWatchlist);
  const affectedSummary = bits.length ? bits.join(' · ') : text.notInHoldingsOrWatchlist;
  return (
    <Card title={text.detailTitle} eyebrow={item.target} level="interactive" padding="md" data-testid={`event-alert-detail-${item.id}`}>
      <div className="space-y-4" data-testid="event-alert-detail">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={item.impactGrade === 'major' ? 'danger' : 'default'}>{item.impactGrade === 'major' ? text.gradeMajor : item.impactGrade === 'routine' ? text.gradeRoutine : text.gradeUnclassified}</Badge>
          <Badge variant="default">{categoryLabel}</Badge>
          {item.degraded ? <Badge variant="warning">{text.degradedNote}</Badge> : null}
        </div>
        <section className="space-y-1">
          <h3 className="text-sm font-medium text-primary-text">{text.whatHappened}</h3>
          <p className="text-sm text-secondary-text" data-testid="event-alert-what-happened">{item.whatHappened || text.noWhatProvided}</p>
        </section>
        <section className="space-y-1">
          <h3 className="text-sm font-medium text-primary-text">{text.whyItMatters}</h3>
          <p className="text-sm text-secondary-text" data-testid="event-alert-why-it-matters">{item.whyItMatters || text.noWhyProvided}</p>
        </section>
        <section className="space-y-2 rounded-md border border-border bg-surface-muted/40 p-3">
          <h3 className="text-sm font-medium text-primary-text">{text.impactContext}</h3>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-muted-text">{text.relatedSymbol}</dt><dd className="font-mono">{item.target}</dd></div>
            <div><dt className="text-xs text-muted-text">{text.eventCategory}</dt><dd>{categoryLabel}</dd></div>
            <div><dt className="text-xs text-muted-text">{text.affectedScope}</dt><dd data-testid="event-alert-affected">{affectedSummary}</dd></div>
            <div><dt className="text-xs text-muted-text">{text.triggeredAt}</dt><dd>{item.triggeredAt ? formatUiDateTime(item.triggeredAt, language, { dateStyle: 'medium', timeStyle: 'short' }) : '--'}</dd></div>
          </dl>
        </section>
        {(item.suggestedActionLabel || item.suggestedActionRationale || item.autoAnalysisStatus) ? (
          <section className="space-y-2 rounded-md border border-border bg-surface-muted/40 p-3" data-testid="event-alert-suggested-action">
            <h3 className="text-sm font-medium text-primary-text">{text.suggestedAction}</h3>
            {item.suggestedActionLabel ? <p className="text-sm text-secondary-text">{item.suggestedActionLabel}</p> : null}
            {item.suggestedActionRationale ? <p className="text-sm text-secondary-text">{item.suggestedActionRationale}</p> : null}
            {item.autoAnalysisStatus ? (
              <p className="text-xs text-muted-text" data-testid="event-alert-auto-analysis-status">
                {text.autoAnalysisStatus}: {item.autoAnalysisStatus}
              </p>
            ) : null}
            {item.suggestedActionLinks?.analysis || item.suggestedActionLinks?.stock_detail ? (
              <div className="flex flex-wrap gap-2 text-sm">
                {item.suggestedActionLinks?.analysis ? (
                  <a className="text-primary underline" href={item.suggestedActionLinks.analysis}>{text.openAnalysis}</a>
                ) : null}
                {item.suggestedActionLinks?.stock_detail ? (
                  <a className="text-primary underline" href={item.suggestedActionLinks.stock_detail}>{text.openStock}</a>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}
        {item.degraded ? <InlineAlert title={text.impactContext} message={text.degradedNote} variant="warning" /> : null}
      </div>
    </Card>
  );
};

export default EventAlertDetail;
