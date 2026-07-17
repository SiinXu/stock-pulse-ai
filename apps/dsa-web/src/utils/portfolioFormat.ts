import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type {
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioFxRefreshResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionItem,
  PortfolioSide,
} from '../types/portfolio';
import { toDateInputValue } from './format';
import type { UiLanguage } from '../i18n/uiText';
import { prefersChineseContent } from '../i18n/uiLanguages';
import { formatUiText } from '../i18n/uiText';
import {
  PORTFOLIO_CASH_DIRECTION_LABELS,
  PORTFOLIO_CORPORATE_ACTION_LABELS,
  PORTFOLIO_SIDE_LABELS,
} from '../locales/portfolio';
import { formatUiNumber } from './uiLocale';

export type FxRefreshFeedback = {
  tone: 'neutral' | 'success' | 'warning';
  text: string;
};

export type PortfolioAlertVariant = 'info' | 'success' | 'warning' | 'danger';

const POSITION_PRICE_LABELS = createUiLanguageRecord('utils.portfolioFormat.POSITION_PRICE_LABELS', {
  zh: { missing: '缺价', realtime: '实时价', close: '收盘价', unknown: '未知来源' },
  en: { missing: 'Price unavailable', realtime: 'Live price', close: 'Close', unknown: 'Unknown source' },
});

const BROKER_FALLBACK_NAMES: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord('utils.portfolioFormat.BROKER_FALLBACK_NAMES', {
  zh: { huatai: '华泰', citic: '中信', cmb: '招商' },
  en: { huatai: 'Huatai', citic: 'CITIC', cmb: 'CMB' },
});

const FX_REFRESH_TEXT = createUiLanguageRecord('utils.portfolioFormat.FX_REFRESH_TEXT', {
  zh: { disabled: '汇率在线刷新已被禁用。', noPairs: '当前范围无可刷新的汇率对。', success: '汇率已刷新，共更新 {count} 对。', summary: '更新 {updated} 对，仍过期 {stale} 对，失败 {errors} 对。', stale: '已尝试刷新，但仍有部分货币对使用 stale/fallback 汇率。{summary}', partial: '在线刷新未完全成功。{summary}' },
  en: { disabled: 'Online FX refresh is disabled.', noPairs: 'There are no FX pairs to refresh in this scope.', success: 'FX rates refreshed. {count} pairs updated.', summary: '{updated} updated, {stale} still stale, {errors} failed.', stale: 'Refresh completed, but some currency pairs still use stale or fallback rates. {summary}', partial: 'Online refresh did not fully succeed. {summary}' },
});

export function getTodayIso(): string {
  return toDateInputValue(new Date());
}

export function formatMoney(value: number | undefined | null, currency = 'CNY', language: UiLanguage = 'zh'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${formatUiNumber(Number(value), language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

export function formatSignedPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function hasPositionPrice(row: PortfolioPositionItem): boolean {
  return row.priceAvailable !== false && row.priceSource !== 'missing';
}

export function formatPositionPrice(row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return '--';
  return row.lastPrice.toFixed(4);
}

export function formatPositionMoney(value: number, row: PortfolioPositionItem, language: UiLanguage = 'zh'): string {
  if (!hasPositionPrice(row)) return '--';
  return formatMoney(value, row.valuationCurrency, language);
}

export function getPositionPriceLabel(row: PortfolioPositionItem, language: UiLanguage = 'zh'): string {
  const labels = POSITION_PRICE_LABELS[language];
  if (!hasPositionPrice(row)) return labels.missing;
  if (row.priceSource === 'realtime_quote') {
    return row.priceProvider ? `${labels.realtime} · ${row.priceProvider}` : labels.realtime;
  }
  if (row.priceSource === 'history_close') {
    return row.priceStale && row.priceDate ? `${labels.close} · ${row.priceDate}` : labels.close;
  }
  return row.priceSource || labels.unknown;
}

export function formatSideLabel(value: PortfolioSide, language: UiLanguage = 'zh'): string {
  return PORTFOLIO_SIDE_LABELS[language][value];
}

export function formatCashDirectionLabel(value: PortfolioCashDirection, language: UiLanguage = 'zh'): string {
  return PORTFOLIO_CASH_DIRECTION_LABELS[language][value];
}

export function formatCorporateActionLabel(value: PortfolioCorporateActionType, language: UiLanguage = 'zh'): string {
  return PORTFOLIO_CORPORATE_ACTION_LABELS[language][value];
}

export function formatBrokerLabel(value: string, displayName?: string, language: UiLanguage = 'zh'): string {
  const name = displayName?.trim() || BROKER_FALLBACK_NAMES[language][value];
  if (name) return prefersChineseContent(language) ? `${value}（${name}）` : `${value} (${name})`;
  return value;
}

export function buildFxRefreshFeedback(data: PortfolioFxRefreshResponse, language: UiLanguage = 'zh'): FxRefreshFeedback {
  const text = FX_REFRESH_TEXT[language];
  if (data.refreshEnabled === false) {
    return {
      tone: 'neutral',
      text: text.disabled,
    };
  }

  if (data.pairCount === 0) {
    return {
      tone: 'neutral',
      text: text.noPairs,
    };
  }

  if (data.updatedCount > 0 && data.staleCount === 0 && data.errorCount === 0) {
    return {
      tone: 'success',
      text: formatUiText(text.success, { count: data.updatedCount }),
    };
  }

  const summary = formatUiText(text.summary, { updated: data.updatedCount, stale: data.staleCount, errors: data.errorCount });
  if (data.staleCount > 0) {
    return {
      tone: 'warning',
      text: formatUiText(text.stale, { summary }),
    };
  }

  return {
    tone: 'warning',
    text: formatUiText(text.partial, { summary }),
  };
}

export function getFxRefreshFeedbackVariant(tone: FxRefreshFeedback['tone']): PortfolioAlertVariant {
  if (tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  return 'info';
}

export function getCsvParseVariant(result: PortfolioImportParseResponse): PortfolioAlertVariant {
  return result.errorCount > 0 || result.skippedCount > 0 ? 'warning' : 'info';
}

export function getCsvCommitVariant(result: PortfolioImportCommitResponse, isDryRun: boolean): PortfolioAlertVariant {
  if (isDryRun) return 'info';
  return result.failedCount > 0 || result.duplicateCount > 0 ? 'warning' : 'success';
}
