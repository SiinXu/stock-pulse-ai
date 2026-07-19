// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { getUiListSeparator } from '../../utils/uiLocale';
import { cn } from '../../utils/cn';
import { resolveAiTaskMatrix, type AiTaskStatus, type UiLang } from './aiTaskMatrix';
import { SETTINGS_MISC_TEXT, SETTINGS_OVERVIEW_STATUS } from '../../locales/settingsMisc';
import { Button, DataTable, Section, type DataTableColumn } from '../common';

interface AiOverviewMatrixProps {
  /** Config value accessor (draft-applied), used to resolve effective routing. */
  getValue: (key: string) => string;
  language: UiLang;
  /** Jump to the Task Routing view to edit models. */
  onEditRouting?: () => void;
  /** Authoritative model routes declared by enabled connections (for Active state). */
  availableRoutes?: Set<string>;
  /** Render an opaque ModelRef as a user-facing model/Connection label. */
  formatModel?: (modelRef: string) => string;
}

const STATUS_META: Record<AiTaskStatus, { dot: string; text: string }> = {
  active: { dot: 'bg-success', text: 'text-foreground' },
  unavailable: { dot: 'bg-danger', text: 'text-danger' },
  unconfigured: { dot: 'bg-warning', text: 'text-warning' },
};

export const AiOverviewMatrix: React.FC<AiOverviewMatrixProps> = ({
  getValue,
  language,
  onEditRouting,
  availableRoutes,
  formatModel = (modelRef) => modelRef,
}) => {
  const rows = resolveAiTaskMatrix(getValue, { availableRoutes });
  const tx = (entry: Record<UiLang, string>) => entry[language];
  const text = SETTINGS_MISC_TEXT[language];
  type AiTaskRow = ReturnType<typeof resolveAiTaskMatrix>[number];
  const columns: DataTableColumn<AiTaskRow>[] = [
    {
      id: 'task',
      header: text.colTask,
      cell: (row) => <span className="font-medium text-foreground">{tx(row.label)}</span>,
    },
    {
      id: 'backend',
      header: text.colBackend,
      cell: (row) => (
        <>
          {tx(row.backendLabel)}
          {row.fallbackBackendId ? (
            <span className="ml-1 text-xs text-muted-text">
              · {text.failover}: {row.fallbackBackendId}
            </span>
          ) : null}
        </>
      ),
      cellClassName: 'text-secondary-text',
    },
    {
      id: 'primary',
      header: text.colPrimary,
      cell: (row) => (
        <>
          {row.primaryModel ? (
            <span className="break-all text-foreground">{formatModel(row.primaryModel)}</span>
          ) : (
            <span className="text-muted-text">{text.none}</span>
          )}
          {row.primaryInherited && row.primaryModel ? (
            <span className="ml-1 text-xs text-muted-text">({text.inherited})</span>
          ) : null}
        </>
      ),
    },
    {
      id: 'fallback',
      header: text.colFallback,
      cell: (row) => row.fallbackModels.length > 0 ? (
        <span className="break-all">
          {row.fallbackModels.map(formatModel).join(getUiListSeparator(language))}
        </span>
      ) : (
        <span className="text-muted-text">—</span>
      ),
      cellClassName: 'text-secondary-text',
    },
    {
      id: 'status',
      header: text.colStatus,
      cell: (row) => (
        <span className="inline-flex items-center gap-1.5">
          <span className={cn('h-2 w-2 rounded-full', STATUS_META[row.status].dot)} aria-hidden="true" />
          <span className={STATUS_META[row.status].text}>
            {SETTINGS_OVERVIEW_STATUS[language][row.status]}
          </span>
        </span>
      ),
    },
  ];

  return (
    <Section
      title={text.overviewTitle}
      description={text.overviewDescription}
      className="[&_h2]:text-sm [&_header_p]:text-xs"
      actions={onEditRouting ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onEditRouting}
          >
            {text.editRouting}
          </Button>
      ) : null}
    >

      <DataTable
        ariaLabel={text.overviewTitle}
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.id}
        emptyState={null}
        loadingLabel={text.overviewTitle}
        scrollClassName="rounded-xl border border-[var(--settings-border)]"
        tableClassName="text-xs"
        headClassName="border-[var(--settings-border)]"
        bodyClassName="divide-[var(--settings-border)]"
        minWidthClassName="min-w-140"
      />
    </Section>
  );
};
