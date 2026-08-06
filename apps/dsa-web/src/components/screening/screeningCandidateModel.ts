import type { AlphaSiftCandidate } from '../../api/alphasift';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { formatUiNumber } from '../../utils/uiLocale';
import type { ScreeningText } from './screeningText';

export const formatScore = (score: AlphaSiftCandidate['score']) => {
  if (score == null || Number.isNaN(Number(score))) {
    return '-';
  }
  return Number(score).toFixed(2);
};

export const formatNumber = (value: unknown, digits = 2) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(digits);
};

export const formatAmount = (value: unknown, language: UiLanguage, text: ScreeningText) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  const amount = Number(value);
  if (Math.abs(amount) >= 100_000_000) {
    return formatUiText(text.amountHundredMillion, { value: formatUiNumber(amount / 100_000_000, language, { maximumFractionDigits: 2 }) });
  }
  if (Math.abs(amount) >= 10_000) {
    return formatUiText(text.amountTenThousand, { value: formatUiNumber(amount / 10_000, language, { maximumFractionDigits: 2 }) });
  }
  return formatUiNumber(amount, language, { maximumFractionDigits: 2 });
};

export const formatPercent = (value: unknown) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
};

export const getCandidateDetailId = (item: AlphaSiftCandidate) => (
  `screening-candidate-${item.rank}-${item.code.replace(/[^a-zA-Z0-9_-]/g, '-')}-details`
);

export const getCandidateReason = (item: AlphaSiftCandidate, text: ScreeningText) => {
  if (item.reason) {
    return item.reason;
  }
  const summaries = item.postAnalysisSummaries || {};
  const summary = Object.values(summaries).find((value) => typeof value === 'string' && value.trim());
  if (typeof summary === 'string') {
    return summary;
  }
  return text.noCandidateSummary;
};

export const getSignal = (item: AlphaSiftCandidate, text: ScreeningText) => {
  const rawSignal = item.raw.action ?? item.raw.signal ?? item.raw.recommendation;
  return typeof rawSignal === 'string' && rawSignal.trim() ? rawSignal : text.observe;
};

export const getFactorEntries = (item: AlphaSiftCandidate) =>
  Object.entries(item.factorScores || {})
    .filter(([, value]) => typeof value === 'number')
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 6);

export const hasLlmInsight = (item: AlphaSiftCandidate) =>
  Boolean(
    item.llmThesis ||
      item.llmSector ||
      item.llmTheme ||
      item.llmConfidence != null ||
      item.llmWatchItems?.length ||
      item.llmCatalysts?.length,
  );
