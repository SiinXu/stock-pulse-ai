// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { EmptyState, Surface } from '../common';
import { DataTable, type DataTableColumn } from '../common/DataTable';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { CHARTS_TEXT } from '../../locales/charts';
import { cn } from '../../utils/cn';
import {
  MAX_RISK_HEATMAP_CELLS,
  MAX_RISK_HEATMAP_COLUMNS,
  MAX_RISK_HEATMAP_ROWS,
  normalizeRiskScore,
  riskScoreFill,
} from './chartUtils';

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

type RiskRow = { id: string; label: string };

const MAX_RISK_HEATMAP_INPUTS = MAX_RISK_HEATMAP_CELLS * 4;

function coordinateKey(rowId: string, columnId: string): string {
  return JSON.stringify([rowId, columnId]);
}

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
  const { rows, columns, matrix } = useMemo(() => {
    const rowMap = new Map<string, string>();
    const columnMap = new Map<string, string>();
    const cellMap = new Map<string, NormalizedCell>();
    for (const rawCell of cells?.slice(0, MAX_RISK_HEATMAP_INPUTS) ?? []) {
      if (!rawCell) continue;
      const rowId = typeof rawCell.rowId === 'string' ? rawCell.rowId.trim() : '';
      const columnId = typeof rawCell.columnId === 'string' ? rawCell.columnId.trim() : '';
      if (!rowId || !columnId) continue;
      if (!rowMap.has(rowId) && rowMap.size >= MAX_RISK_HEATMAP_ROWS) continue;
      if (!columnMap.has(columnId) && columnMap.size >= MAX_RISK_HEATMAP_COLUMNS) continue;
      const rowLabel = typeof rawCell.rowLabel === 'string' && rawCell.rowLabel.trim()
        ? rawCell.rowLabel.trim()
        : rowId;
      const columnLabel = typeof rawCell.columnLabel === 'string' && rawCell.columnLabel.trim()
        ? rawCell.columnLabel.trim()
        : columnId;
      if (!rowMap.has(rowId)) rowMap.set(rowId, rowLabel);
      if (!columnMap.has(columnId)) columnMap.set(columnId, columnLabel);
      // The last valid declaration wins for duplicate row/column coordinates.
      cellMap.set(coordinateKey(rowId, columnId), {
        rowId,
        rowLabel: rowMap.get(rowId) as string,
        columnId,
        columnLabel: columnMap.get(columnId) as string,
        score: normalizeRiskScore(rawCell.score),
      });
    }
    return {
      rows: [...rowMap.entries()].map(([id, label]) => ({ id, label })),
      columns: [...columnMap.entries()].map(([id, label]) => ({ id, label })),
      matrix: cellMap,
    };
  }, [cells]);

  if (rows.length === 0 || columns.length === 0) {
    return (
      <div className={className} data-testid={testId}>
        <EmptyState data-testid={`${testId}-empty`} title={text.riskEmptyTitle} description={text.riskEmptyDescription} />
      </div>
    );
  }
  const ariaLabel = formatUiText(text.riskChartLabel, { rows: String(rows.length), columns: String(columns.length) });
  const tableColumns: DataTableColumn<RiskRow>[] = [
    {
      id: 'dimension',
      header: text.riskDimension,
      rowHeader: true,
      nowrap: true,
      cell: (row) => <span className="font-medium text-foreground">{row.label}</span>,
    },
    ...columns.map((column): DataTableColumn<RiskRow> => ({
      id: `risk:${column.id}`,
      header: column.label,
      align: 'center',
      cell: (row) => {
        const cell = matrix.get(coordinateKey(row.id, column.id));
        const score = cell?.score ?? null;
        const fill = riskScoreFill(score);
        const level = levelLabel(fill.level, text);
        const scoreText = score === null ? text.riskMissing : score.toFixed(0);
        const cellLabel = formatUiText(text.riskScore, { score: scoreText });
        return (
          <div
            data-testid={`${testId}-cell-${row.id}-${column.id}`}
            data-risk-level={fill.level}
            aria-label={`${row.label}, ${column.label}, ${cellLabel}, ${level}`}
            className={cn(
              'flex min-h-14 flex-col items-center justify-center rounded-md border border-border/60 px-1 py-1 text-center',
              fill.textClass,
            )}
            style={{ background: fill.background }}
          >
            <span className="text-sm font-semibold tabular-nums">{scoreText}</span>
            <span className="text-label leading-tight text-muted-text">{level}</span>
          </div>
        );
      },
    })),
  ];
  return (
    <div className={className} data-testid={testId}>
      <Surface level="section" padding="sm" className="flex flex-col gap-3" data-testid={`${testId}-surface`}>
      <p className="text-xs text-muted-text" data-testid={`${testId}-legend`}>{text.riskLegend}</p>
      <div data-testid={`${testId}-grid`}>
        <DataTable
          caption={ariaLabel}
          scrollAreaLabel={ariaLabel}
          columns={tableColumns}
          rows={rows}
          getRowKey={(row) => row.id}
          getRowTestId={(row) => `${testId}-row-${row.id}`}
          emptyState={{ title: text.riskEmptyTitle, description: text.riskEmptyDescription }}
          density="compact"
          frame="embedded"
          minWidth="container"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-label text-muted-text" aria-hidden="true">
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
    </div>
  );
};
RiskHeatmap.displayName = 'RiskHeatmap';
