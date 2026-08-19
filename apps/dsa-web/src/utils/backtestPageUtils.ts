import {
  BACKTEST_PHASE_LABELS,
  BACKTEST_RESOLUTION_NOTE_LABELS,
} from '../locales/backtest';
import type { BacktestResultItem } from '../types/backtest';
import type { UiLanguage } from '../i18n/uiText';
import { RESEARCH_BACKTEST_LIMITS } from '../routing/routes';
import { getMarketPhaseSummaryLabel, stripMarketPhaseSummaryPrefix } from './marketPhase';

export function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

export function phaseLabel(row: BacktestResultItem, language: UiLanguage): string {
  const label = getMarketPhaseSummaryLabel(row.marketPhaseSummary, language);
  if (label) {
    return stripMarketPhaseSummaryPrefix(label) ?? label;
  }
  return (row.marketPhase ? BACKTEST_PHASE_LABELS[language][row.marketPhase] : undefined) || row.marketPhase || '--';
}

export function normalizeBacktestCode(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.toUpperCase();
}

export function parseEvalWindowDays(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > RESEARCH_BACKTEST_LIMITS.maxWindowDays) {
    return undefined;
  }

  return parsed;
}

export function parseBoundedInteger(value: string, min: number, max: number): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    return undefined;
  }
  return parsed;
}

export function formatResolutionNotes(notes: string | null | undefined, language: UiLanguage): string[] {
  if (!notes) return [];
  const labels = BACKTEST_RESOLUTION_NOTE_LABELS[language];
  return notes
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => labels[part] ?? part);
}

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day;
}

export function labelFromMap(value: string | null | undefined, labels: Record<string, string>): string {
  if (!value) return '--';
  return labels[value] ?? value;
}
