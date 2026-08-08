// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { EmptyState, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { CHARTS_TEXT } from '../../locales/charts';
import { cn } from '../../utils/cn';
import { normalizeRiskScore, riskScoreFill } from './chartUtils';

export type RiskHeatmapCell = {
  rowId: string;
  rowLabel: string;
  columnId: string;
  columnLabel: string;
  score: number | null | undefined;
};

export type RiskHeatmapProps = {
  cells: readonly RiskHeatmapCell[] | null | undefined;
  className?: string;
  'data-testid'?: string;
};

type NormalizedCell = {
  rowId: string; rowLabel: string; columnId: string; columnLabel: string; score: number | null;
};

function levelLabel(level: ReturnType<typeof riskScoreFill>['level'], text: (typeof CHARTS_TEXT)['en']): string {
  switch (level) {
    case 'low': return text.riskLevelLow;
    case 'medium': return text.riskLevelMedium;
    case 'high': return text.riskLevelHigh;
    case 'critical': return text.riskLevelCritical;
    default: return text.riskMissing;
  }
}

export const RiskHeatmap: React.FC<RiskHeatmapProps> = ({
  cells, className, 'data-testid': testId = 'risk-heatmap',
}) => {
  const { language } = useUiLanguage();
  const text = CHARTS_TEXT[language];
  const normalized = useMemo((): NormalizedCell[] => {
    if (!cells || cells.length === 0) return [];
    return cells.filter((c) => c && c.rowId && c.columnId).map((c) => ({
      rowId: c.rowId, rowLabel: c.rowLabel || c.rowId,
      columnId: c.columnId, columnLabel: c.columnLabel || c.columnId,
      score: normalizeRiskScore(c.score),
    }));
  }, [cells]);
  const { rows, columns, matrix } = useMemo(() => {
    const rowMap = new Map<string, string>();
    const columnMap = new Map<string, string>();
    const cellMap = new Map<string, NormalizedCell>();
    for (const cell of normalized) {
      if (!rowMap.has(cell.rowId)) rowMap.set(cell.rowId, cell.rowLabel);
      if (!columnMap.has(cell.columnId)) columnMap.set(cell.columnId, cell.columnLabel);
      cellMap.set(`${cell.rowId}::${cell.columnId}`, cell);
    }
    return {
      rows: [...rowMap.entries()].map(([id, label]) => ({ id, label })),
      columns: [...columnMap.entries()].map(([id, label]) => ({ id, label })),
      matrix: cellMap,
    };
  }, [normalized]);

  if (rows.length === 0 || columns.length === 0) {
    return <EmptyState data-testid={`${testId}-empty`} title={text.riskEmptyTitle} description={text.riskEmptyDescription} className={className} />;
  }
  const ariaLabel = formatUiText(text.riskChartLabel, { rows: String(rows.length), columns: String(columns.length) });
  return (
    <Surface level="section" padding="sm" className={cn('flex flex-col gap-3', className)} data-testid={testId}>
      <p className="text-xs text-muted-text" data-testid={`${testId}-legend`}>{text.riskLegend}</p>
      <div role="table" aria-label={ariaLabel} className="w-full overflow-x-auto" data-testid={`${testId}-grid`}>
        <div role="rowgroup" className="inline-grid min-w-full gap-1"
          style={{ gridTemplateColumns: `minmax(5.5rem, max-content) repeat(${columns.length}, minmax(4.5rem, 1fr))` }}>
          <div role="row" className="contents">
            <div role="columnheader" className="px-1 py-1 text-xs font-medium text-muted-text" />
            {columns.map((column) => (
              <div key={column.id} role="columnheader" className="px-1 py-1 text-center text-xs font-medium text-muted-text">{column.label}</div>
            ))}
          </div>
          {rows.map((row) => (
            <div key={row.id} role="row" className="contents">
              <div role="rowheader" className="flex items-center px-1 py-1 text-xs font-medium text-foreground">{row.label}</div>
              {columns.map((column) => {
                const cell = matrix.get(`${row.id}::${column.id}`);
                const score = cell?.score ?? null;
                const fill = riskScoreFill(score);
                const level = levelLabel(fill.level, text);
                const scoreText = score === null ? text.riskMissing : score.toFixed(0);
                const cellLabel = formatUiText(text.riskScore, { score: scoreText });
                return (
                  <div key={`${row.id}-${column.id}`} role="cell"
                    data-testid={`${testId}-cell-${row.id}-${column.id}`} data-risk-level={fill.level}
                    title={`${row.label} · ${column.label}: ${cellLabel} (${level})`}
                    aria-label={`${row.label}, ${column.label}, ${cellLabel}, ${level}`}
                    className={cn('flex min-h-14 flex-col items-center justify-center rounded-md border border-border/60 px-1 py-1 text-center', fill.textClass)}
                    style={{ background: fill.background }}>
                    <span className="text-sm font-semibold tabular-nums">{scoreText}</span>
                    <span className="text-[10px] leading-tight text-muted-text">{level}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-text" aria-hidden="true">
        {([['low', 12, text.riskLevelLow], ['medium', 40, text.riskLevelMedium], ['high', 65, text.riskLevelHigh], ['critical', 90, text.riskLevelCritical]] as const).map(([level, sample, label]) => {
          const fill = riskScoreFill(sample);
          return (
            <span key={level} className="inline-flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm border border-border/50" style={{ background: fill.background }} />
              {label}
            </span>
          );
        })}
      </div>
    </Surface>
  );
};
RiskHeatmap.displayName = 'RiskHeatmap';
