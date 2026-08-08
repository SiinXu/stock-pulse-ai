// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Activity } from 'lucide-react';
import { Badge, Card, DataTable, type DataTableColumn } from '../common';
import type { EventAlertDisplayItem, EventAlertImpactGrade } from '../../types/eventAlerts';
import { isCorporateEventCategory } from '../../utils/eventAlertContext';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVENT_ALERT_PAGE_TEXT, EVENT_CATEGORY_LABELS } from '../../locales/eventAlerts';
import { formatUiDateTime } from '../../utils/uiLocale';

export interface EventAlertListProps {
  items: EventAlertDisplayItem[];
  isLoading?: boolean;
  selectedId?: number | null;
  onSelect?: (item: EventAlertDisplayItem) => void;
  gradeFilter?: 'all' | EventAlertImpactGrade;
}

export const EventAlertList: React.FC<EventAlertListProps> = ({
  items, isLoading = false, selectedId = null, onSelect, gradeFilter = 'all',
}) => {
  const { language } = useUiLanguage();
  const text = EVENT_ALERT_PAGE_TEXT[language];
  const categoryLabels = EVENT_CATEGORY_LABELS[language];
  const visible = gradeFilter === 'all' ? items : items.filter((item) => item.impactGrade === gradeFilter);
  const columns: DataTableColumn<EventAlertDisplayItem>[] = [
    { id: 'grade', header: text.status, cell: (item) => (
      <Badge variant={item.impactGrade === 'major' ? 'danger' : 'default'}>
        {item.impactGrade === 'major' ? text.gradeMajor : text.gradeRoutine}
      </Badge>
    )},
    { id: 'category', header: text.eventCategory, cell: (item) => (
      <span data-testid={`event-alert-category-${item.id}`}>
        {isCorporateEventCategory(item.eventCategory) ? categoryLabels[item.eventCategory] : '--'}
      </span>
    )},
    { id: 'target', header: text.relatedSymbol, cell: (item) => (
      <span className="font-mono" data-testid={`event-alert-target-${item.id}`}>{item.target}</span>
    )},
    { id: 'why', header: text.whyItMatters, cell: (item) => (
      <div className="max-w-md text-sm" data-testid={`event-alert-why-${item.id}`}>{item.whyItMatters || text.noWhyProvided}</div>
    )},
    { id: 'time', header: text.triggeredAt, cell: (item) => (
      <span className="text-xs">{item.triggeredAt ? formatUiDateTime(item.triggeredAt, language, { dateStyle: 'medium', timeStyle: 'short' }) : '--'}</span>
    )},
  ];
  const table = (
    <DataTable<EventAlertDisplayItem>
      caption={text.listTitle}
      columns={columns}
      rows={visible}
      getRowKey={(item) => item.id}
      isRowSelected={(item) => item.id === selectedId}
      getRowTestId={(item) => `event-alert-row-${item.id}`}
      status={isLoading ? { state: 'loading', title: text.loading } : undefined}
      emptyState={{ icon: <Activity className="h-6 w-6" />, title: text.emptyTitle, description: text.emptyDescription }}
      density="compact"
      minWidth="wide"
      {...(onSelect ? {
        onRowActivate: (item: EventAlertDisplayItem) => onSelect(item),
        getRowAriaLabel: (item: EventAlertDisplayItem) => `${item.target} ${item.eventCategory ?? ''}`.trim(),
      } : {})}
    />
  );
  return <Card title={text.listTitle} variant="bordered" padding="md">{table}</Card>;
};
