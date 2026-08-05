// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import type {
  SkillOutcomeItem,
  SkillOutcomeSampleItem,
} from '../../api/skillOutcomes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SKILL_OUTCOMES_TEXT } from '../../locales/skillOutcomes';
import { getUiLocale } from '../../utils/uiLocale';
import {
  Badge,
  DataTable,
  type DataTableColumn,
  EmptyState,
  Surface,
} from '../common';

function formatPct(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value)}%`;
}

function evalStatusVariant(status: string): 'default' | 'success' | 'warning' | 'history' | 'danger' {
  switch (status) {
    case 'evaluated':
      return 'success';
    case 'pending':
      return 'warning';
    case 'observational':
      return 'history';
    case 'unable':
      return 'danger';
    default:
      return 'default';
  }
}

export interface SkillOutcomeRecentListsProps {
  outcomes: SkillOutcomeItem[];
  samples: SkillOutcomeSampleItem[];
}

export const SkillOutcomeRecentLists: React.FC<SkillOutcomeRecentListsProps> = ({
  outcomes,
  samples,
}) => {
  const { language } = useUiLanguage();
  const text = SKILL_OUTCOMES_TEXT[language];
  const locale = getUiLocale(language);

  const outcomeColumns = useMemo<DataTableColumn<SkillOutcomeItem>[]>(() => [
    {
      id: 'skill',
      header: text.colSkill,
      cell: (item) => <span className="font-mono text-sm">{item.skillId}</span>,
    },
    {
      id: 'stock',
      header: text.colStock,
      cell: (item) => <span className="font-mono text-sm">{item.stockCode}</span>,
    },
    {
      id: 'horizon',
      header: text.colHorizon,
      cell: (item) => item.horizon || '—',
    },
    {
      id: 'signal',
      header: text.colSignal,
      cell: (item) => item.signal || '—',
    },
    {
      id: 'evalStatus',
      header: text.colEvalStatus,
      cell: (item) => (
        <Badge variant={evalStatusVariant(item.evalStatus)} size="sm">
          {item.evalStatus}
        </Badge>
      ),
    },
    {
      id: 'outcome',
      header: text.colOutcome,
      cell: (item) => item.outcome ?? '—',
    },
    {
      id: 'return',
      header: text.colReturn,
      cell: (item) => (
        <span className="tabular-nums">{formatPct(item.directionalReturnPct, locale)}</span>
      ),
    },
    {
      id: 'unableReason',
      header: text.colUnableReason,
      cell: (item) => (
        <span className="text-xs text-secondary-text">{item.unableReason ?? '—'}</span>
      ),
    },
  ], [locale, text]);

  const sampleColumns = useMemo<DataTableColumn<SkillOutcomeSampleItem>[]>(() => [
    {
      id: 'skill',
      header: text.colSkill,
      cell: (item) => <span className="font-mono text-sm">{item.skillId}</span>,
    },
    {
      id: 'stock',
      header: text.colStock,
      cell: (item) => <span className="font-mono text-sm">{item.stockCode}</span>,
    },
    {
      id: 'signal',
      header: text.colSignal,
      cell: (item) => item.signal || '—',
    },
    {
      id: 'confidence',
      header: text.colConfidence,
      cell: (item) => (
        <span className="tabular-nums">
          {Number.isFinite(item.confidence)
            ? new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(item.confidence)
            : '—'}
        </span>
      ),
    },
    {
      id: 'history',
      header: text.colHistoryId,
      cell: (item) => (
        <span className="font-mono text-xs text-secondary-text">#{item.analysisHistoryId}</span>
      ),
    },
  ], [locale, text]);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Surface as="section" level="section" padding="md" className="space-y-3" data-testid="skill-outcome-recent-outcomes">
        <h3 className="text-sm font-semibold text-foreground">{text.recentOutcomesTitle}</h3>
        {outcomes.length === 0 ? (
          <EmptyState compact title={text.recentOutcomesEmpty} />
        ) : (
          <DataTable
            caption={text.recentOutcomesTitle}
            columns={outcomeColumns}
            rows={outcomes}
            getRowKey={(item) => item.id}
            emptyState={{ title: text.recentOutcomesEmpty }}
            density="compact"
            frame="embedded"
            minWidth="wide"
          />
        )}
      </Surface>

      <Surface as="section" level="section" padding="md" className="space-y-3" data-testid="skill-outcome-recent-samples">
        <h3 className="text-sm font-semibold text-foreground">{text.samplesTitle}</h3>
        {samples.length === 0 ? (
          <EmptyState compact title={text.samplesEmpty} />
        ) : (
          <DataTable
            caption={text.samplesTitle}
            columns={sampleColumns}
            rows={samples}
            getRowKey={(item) => item.id}
            emptyState={{ title: text.samplesEmpty }}
            density="compact"
            frame="embedded"
            minWidth="wide"
          />
        )}
      </Surface>
    </div>
  );
};
