// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import type { SkillOutcomePerformanceBucket } from '../../api/skillOutcomes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SKILL_OUTCOMES_TEXT } from '../../locales/skillOutcomes';
import { getUiLocale } from '../../utils/uiLocale';
import { Badge, DataTable, type DataTableColumn } from '../common';

function formatPct(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  }).format(value)}%`;
}

function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return String(value);
}

export interface SkillOutcomePerformanceTableProps {
  buckets: SkillOutcomePerformanceBucket[];
}

export const SkillOutcomePerformanceTable: React.FC<SkillOutcomePerformanceTableProps> = ({
  buckets,
}) => {
  const { language } = useUiLanguage();
  const text = SKILL_OUTCOMES_TEXT[language];
  const locale = getUiLocale(language);

  const columns = useMemo<DataTableColumn<SkillOutcomePerformanceBucket>[]>(() => [
    {
      id: 'skill',
      header: text.colSkill,
      cell: (bucket) => (
        <span className="font-mono text-sm text-foreground">{bucket.skillId || '—'}</span>
      ),
    },
    {
      id: 'horizon',
      header: text.colHorizon,
      cell: (bucket) => bucket.horizon || '—',
    },
    {
      id: 'engine',
      header: text.colEngine,
      cell: (bucket) => (
        <span className="font-mono text-xs text-secondary-text">{bucket.engineVersion || '—'}</span>
      ),
    },
    {
      id: 'status',
      header: text.colStatus,
      cell: (bucket) => (
        <Badge variant={bucket.sampleSufficient ? 'success' : 'history'} size="sm">
          {bucket.sampleSufficient ? text.statusSufficient : text.statusInsufficient}
        </Badge>
      ),
    },
    {
      id: 'total',
      header: text.colTotal,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.total)}</span>
      ),
    },
    {
      id: 'pending',
      header: text.colPending,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.pending)}</span>
      ),
    },
    {
      id: 'evaluated',
      header: text.colEvaluated,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.evaluated)}</span>
      ),
    },
    {
      id: 'observational',
      header: text.colObservational,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.observational)}</span>
      ),
    },
    {
      id: 'unable',
      header: text.colUnable,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.unable)}</span>
      ),
    },
    {
      id: 'hit',
      header: text.colHit,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.hit)}</span>
      ),
    },
    {
      id: 'miss',
      header: text.colMiss,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.miss)}</span>
      ),
    },
    {
      id: 'hitRate',
      header: text.colHitRate,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text" data-testid="skill-outcome-hit-rate">
          {bucket.sampleSufficient
            ? formatPct(bucket.hitRatePct, locale)
            : text.ratesHidden}
        </span>
      ),
    },
    {
      id: 'missRate',
      header: text.colMissRate,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">
          {bucket.sampleSufficient
            ? formatPct(bucket.missRatePct, locale)
            : text.ratesHidden}
        </span>
      ),
    },
    {
      id: 'avgReturn',
      header: text.colAvgReturn,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">
          {bucket.sampleSufficient
            ? formatPct(bucket.avgDirectionalReturnPct, locale)
            : text.ratesHidden}
        </span>
      ),
    },
    {
      id: 'unableRate',
      header: text.colUnableRate,
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">
          {bucket.sampleSufficient
            ? formatPct(bucket.unableRatePct, locale)
            : text.ratesHidden}
        </span>
      ),
    },
  ], [locale, text]);

  return (
    <div data-testid="skill-outcome-performance-table">
      <DataTable
        caption={text.statsTitle}
        columns={columns}
        rows={buckets}
        getRowKey={(bucket) => `${bucket.skillId}:${bucket.horizon}:${bucket.engineVersion}`}
        emptyState={{
          title: text.statusInsufficient,
        }}
        density="compact"
        frame="embedded"
        minWidth="extra-wide"
      />
    </div>
  );
};
