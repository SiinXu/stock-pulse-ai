// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type {
  PortfolioImportCommitResponse,
  PortfolioImportFailedRow,
  PortfolioImportParseResponse,
} from '../../types/portfolio';
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../../i18n/uiText';
import { prefersChineseContent } from '../../i18n/uiLanguages';

export type PortfolioImportAlertVariant = 'info' | 'success' | 'warning' | 'danger';

const BROKER_FALLBACK_NAMES: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord('utils.portfolioFormat.BROKER_FALLBACK_NAMES', {
  zh: { huatai: '华泰', citic: '中信', cmb: '招商' },
  en: { huatai: 'Huatai', citic: 'CITIC', cmb: 'CMB' },
});

export function formatBrokerLabel(
  value: string,
  displayName?: string,
  language: UiLanguage = 'zh',
): string {
  const name = displayName?.trim() || BROKER_FALLBACK_NAMES[language][value];
  if (!name) return value;
  return prefersChineseContent(language) ? `${value}（${name}）` : `${value} (${name})`;
}

export function getCsvParseVariant(
  result: PortfolioImportParseResponse,
): PortfolioImportAlertVariant {
  return result.errorCount > 0
    || result.skippedCount > 0
    || Boolean(result.failedRows?.length)
    ? 'warning'
    : 'info';
}

export function getCsvCommitVariant(
  result: PortfolioImportCommitResponse,
  isDryRun: boolean,
): PortfolioImportAlertVariant {
  if (isDryRun) return 'info';
  return result.failedCount > 0 || result.duplicateCount > 0 ? 'warning' : 'success';
}

function escapeCsvCell(value: string): string {
  const safeValue = /^\s*[=+\-@]/.test(value) ? `'${value}` : value;
  if (/[",\n\r]/.test(safeValue)) {
    return `"${safeValue.replace(/"/g, '""')}"`;
  }
  return safeValue;
}

/** Build a BOM-prefixed UTF-8 correction file without executable spreadsheet cells. */
export function buildFailedRowsCsv(
  failedRows: readonly PortfolioImportFailedRow[],
): string {
  const sourceKeys = new Set<string>();
  for (const row of failedRows) {
    Object.keys(row.source ?? {}).forEach((key) => sourceKeys.add(key));
  }
  const orderedSourceKeys = [...sourceKeys];
  const headers = ['row_number', 'reason_code', 'reason', ...orderedSourceKeys];
  const lines = [headers.map(escapeCsvCell).join(',')];

  for (const row of failedRows) {
    const source = row.source ?? {};
    const cells = [
      String(row.rowNumber),
      row.reasonCode,
      row.reason,
      ...orderedSourceKeys.map((key) => source[key] ?? ''),
    ];
    lines.push(cells.map((cell) => escapeCsvCell(String(cell))).join(','));
  }

  return `\uFEFF${lines.join('\n')}\n`;
}

export function downloadTextFile(
  filename: string,
  content: string,
  mimeType = 'text/csv;charset=utf-8',
): void {
  if (typeof document === 'undefined') return;
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
