import type { UiLanguage } from '../i18n/uiText';
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import { getUiLocale } from './uiLocale';

const SERVER_LOCAL_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

function normalizeShanghaiDateTime(value: string): string {
  const trimmed = value.trim();
  return SERVER_LOCAL_DATE_TIME_PATTERN.test(trimmed)
    ? `${trimmed.replace(' ', 'T')}+08:00`
    : trimmed;
}

export function getShanghaiDateKey(value?: string | null): string {
  if (!value) return '';
  const date = new Date(normalizeShanghaiDateTime(value));
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(date);
}

export function getShanghaiTimeValue(value?: string | null): number {
  if (!value) return 0;
  const date = new Date(normalizeShanghaiDateTime(value));
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

export const formatDateTime = (value?: string | null, language: UiLanguage = 'zh'): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatDate = (value?: string, language: UiLanguage = 'zh'): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
};

export const toDateInputValue = (date: Date): string => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * Returns the date N days ago as YYYY-MM-DD in Asia/Shanghai timezone.
 * Consistent with getTodayInShanghai() so both ends of the date range
 * are expressed in the same timezone as the backend.
 */
export const getRecentStartDate = (days: number): string => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(date);
};

/**
 * Returns today's date as YYYY-MM-DD in Asia/Shanghai timezone.
 * Use this instead of the browser-local date for market-day UI semantics.
 */
export const getTodayInShanghai = (): string =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());

const REPORT_TYPE_LABELS = createUiLanguageRecord('utils.format.REPORT_TYPE_LABELS', {
  zh: { simple: '普通', detailed: '标准', full: '完整', brief: '简版', market_review: '大盘' },
  en: { simple: 'Standard', detailed: 'Detailed', full: 'Full', brief: 'Brief', market_review: 'Market review' },
});

export const formatReportType = (value?: string, language: UiLanguage = 'zh'): string => {
  if (!value) return '—';
  const labels = REPORT_TYPE_LABELS[language];
  if (value in labels) return labels[value as keyof typeof labels];
  return value;
};
