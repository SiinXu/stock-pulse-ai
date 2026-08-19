// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { ALERT_SEVERITY_LABELS } from '../../locales/alerts';
import { getPortfolioInsightCodes } from '../../locales/portfolioInsightCodes';
import type { PortfolioHealthInsight } from '../../types/portfolioHealth';
import type { StressScenario } from '../../types/portfolioInsights';
import { formatDataQualityStatus } from './portfolio';
import {
  formatEmptyDisplay,
  formatLabeledDiagnostic,
  formatUnknownMachineCode,
  sanitizeDiagnosticText,
} from './unknownCode';

const BAND_KEYS = {
  healthy: 'bandHealthy',
  fair: 'bandFair',
  caution: 'bandCaution',
  poor: 'bandPoor',
} as const;

const INSIGHT_KEYS = {
  concentration_top_name: 'insightConcentrationTopName',
  concentration_name: 'insightConcentrationName',
  low_diversification: 'insightLowDiversification',
  elevated_var: 'insightElevatedVar',
  cash_low: 'insightCashLow',
  cash_high: 'insightCashHigh',
  unrealized_loss: 'insightUnrealizedLoss',
  within_thresholds: 'insightWithinThresholds',
  concentration_unavailable: 'insightConcentrationUnavailable',
  risk_exposure_unavailable: 'insightRiskExposureUnavailable',
  diversification_unavailable: 'insightDiversificationUnavailable',
  pnl_unavailable: 'insightPnlUnavailable',
  cash_ratio_unavailable: 'insightCashRatioUnavailable',
} as const;

const DIMENSION_REASON_KEYS = {
  concentration_block_unavailable: 'reasonConcentrationBlockUnavailable',
  diversification_unavailable: 'reasonDiversificationUnavailable',
  synthetic_basket_no_holdings_pnl: 'reasonSyntheticBasketNoHoldingsPnl',
  price_or_fx_quality_partial: 'reasonPriceOrFxQualityPartial',
  zero_equity: 'reasonZeroEquity',
  synthetic_basket_no_cash_ledger: 'reasonSyntheticBasketNoCashLedger',
  fx_stale: 'reasonFxStale',
} as const;

const ACTION_KEYS = {
  trim: 'actionTrim',
  add: 'actionAdd',
  hold: 'actionHold',
  reduce: 'actionReduce',
  exit: 'actionExit',
} as const;

const RATIONALE_KEYS = {
  trim: 'rationaleTrim',
  add: 'rationaleAdd',
  hold: 'rationaleHold',
  reduce: 'rationaleReduce',
  exit: 'rationaleExit',
} as const;

const SCENARIO_KEYS = {
  market_down_10: ['scenarioMarketDown10Name', 'scenarioMarketDown10Description'],
  market_down_20: ['scenarioMarketDown20Name', 'scenarioMarketDown20Description'],
  sector_down_30: ['scenarioSectorDown30Name', 'scenarioSectorDown30Description'],
  fx_up_5: ['scenarioFxUp5Name', 'scenarioFxUp5Description'],
  fx_down_5: ['scenarioFxDown5Name', 'scenarioFxDown5Description'],
  rate_up_100bp: ['scenarioRateUp100bpName', 'scenarioRateUp100bpDescription'],
} as const;

function codes(language: UiLanguage) {
  return getPortfolioInsightCodes(language);
}

function formatFinite(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(digits);
}

export function formatPortfolioHealthBand(
  band: string | null | undefined,
  language: UiLanguage,
): string {
  if (band == null || band === '') return formatEmptyDisplay();
  const key = BAND_KEYS[band as keyof typeof BAND_KEYS];
  if (key) return codes(language)[key];
  return formatUnknownMachineCode(band, language);
}

export function formatPortfolioInsightSeverity(
  severity: string | null | undefined,
  language: UiLanguage,
): string {
  if (severity == null || severity === '') return formatEmptyDisplay();
  const labels = ALERT_SEVERITY_LABELS[language];
  return labels[severity] ?? formatUnknownMachineCode(severity, language);
}

export function formatPortfolioHealthInsight(
  insight: Pick<PortfolioHealthInsight, 'code' | 'symbol' | 'value' | 'threshold'>,
  language: UiLanguage,
): string {
  const catalog = codes(language);
  const code = String(insight.code ?? '').trim();
  if (!code) return formatEmptyDisplay();
  const key = INSIGHT_KEYS[code as keyof typeof INSIGHT_KEYS];
  if (!key) return formatUnknownMachineCode(code, language);
  return formatUiText(catalog[key], {
    symbol: insight.symbol || '—',
    value: formatFinite(insight.value, code === 'low_diversification' ? 2 : 1),
    threshold: formatFinite(insight.threshold, code === 'low_diversification' ? 2 : 1),
  });
}

export function formatPortfolioDimensionDetail(
  row: { status?: string | null; reason?: string | null; statusMessage?: string | null },
  language: UiLanguage,
): string {
  const reason = String(row.reason ?? '').trim();
  if (reason) {
    const key = DIMENSION_REASON_KEYS[reason as keyof typeof DIMENSION_REASON_KEYS];
    if (key) return codes(language)[key];
    if (reason === 'ok' || reason === 'unavailable' || reason === 'partial') {
      return formatDataQualityStatus(reason, language);
    }
    return formatUnknownMachineCode(reason, language);
  }
  if (row.status) return formatDataQualityStatus(row.status, language);
  return formatEmptyDisplay();
}

export function formatPortfolioRebalanceAction(
  action: string | null | undefined,
  language: UiLanguage,
): string {
  if (action == null || action === '') return formatEmptyDisplay();
  const key = ACTION_KEYS[action as keyof typeof ACTION_KEYS];
  if (key) return codes(language)[key];
  return formatUnknownMachineCode(action, language);
}

export function formatPortfolioRebalanceRationale(
  row: {
    action?: string | null;
    symbol?: string | null;
    fromWeightPct?: number | null;
    toWeightPct?: number | null;
    currentWeightPct?: number | null;
    targetWeightPctLow?: number | null;
    targetWeightPctHigh?: number | null;
  },
  language: UiLanguage,
): string {
  const catalog = codes(language);
  const action = String(row.action ?? '').trim();
  const rationaleKey = RATIONALE_KEYS[action as keyof typeof RATIONALE_KEYS];
  const symbol = row.symbol || '—';
  if (row.currentWeightPct != null && row.targetWeightPctLow != null && row.targetWeightPctHigh != null) {
    return formatUiText(catalog.rationaleBand, {
      symbol,
      current: formatFinite(row.currentWeightPct),
      low: formatFinite(row.targetWeightPctLow),
      high: formatFinite(row.targetWeightPctHigh),
    });
  }
  if (rationaleKey) {
    return formatUiText(catalog[rationaleKey], {
      symbol,
      from: formatFinite(row.fromWeightPct),
      to: formatFinite(row.toWeightPct),
    });
  }
  if (!action) return formatEmptyDisplay();
  return formatUnknownMachineCode(action, language);
}

export function formatPortfolioInsightStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  if (status == null || status === '') return formatEmptyDisplay();
  if (status === 'insufficient_data') return codes(language).statusInsufficientData;
  if (status === 'refused') return codes(language).statusRefused;
  return formatDataQualityStatus(status, language);
}

export function formatPortfolioInsightDisclaimer(
  kind: 'health' | 'basket' | 'rebalance',
  language: UiLanguage,
): string {
  const catalog = codes(language);
  if (kind === 'health') return catalog.disclaimerHealth;
  if (kind === 'basket') return catalog.disclaimerBasket;
  return catalog.disclaimerRebalance;
}

export function formatPortfolioBasketReason(
  reason: string | null | undefined,
  language: UiLanguage,
): string {
  if (reason == null || reason === '') return formatEmptyDisplay();
  if (reason === 'price_unavailable') return codes(language).basketPriceUnavailable;
  return formatUnknownMachineCode(reason, language);
}

export function formatPortfolioBasketDirection(
  direction: string | null | undefined,
  language: UiLanguage,
): string {
  if (direction == null || direction === '') return formatEmptyDisplay();
  if (direction === 'positive') return codes(language).directionPositive;
  if (direction === 'negative') return codes(language).directionNegative;
  return formatUnknownMachineCode(direction, language);
}

export function formatPortfolioSharedRisk(
  row: { kind?: string | null; size?: number | null; sector?: string | null; topWeightPct?: number | null },
  language: UiLanguage,
): { kindLabel: string; summary: string } {
  const catalog = codes(language);
  const kind = String(row.kind ?? '').trim();
  if (kind === 'high_correlation_cluster') {
    return {
      kindLabel: catalog.kindHighCorrelation,
      summary: formatUiText(catalog.sharedHighCorrelation, { size: row.size ?? '—' }),
    };
  }
  if (kind === 'sector_concentration') {
    return {
      kindLabel: catalog.kindSectorConcentration,
      summary: formatUiText(catalog.sharedSectorConcentration, {
        size: row.size ?? '—',
        sector: sanitizeDiagnosticText(String(row.sector || '—'), 80),
      }),
    };
  }
  if (kind === 'name_concentration') {
    return {
      kindLabel: catalog.kindNameConcentration,
      summary: formatUiText(catalog.sharedNameConcentration, {
        weight: formatFinite(row.topWeightPct),
      }),
    };
  }
  if (!kind) {
    return { kindLabel: formatEmptyDisplay(), summary: formatEmptyDisplay() };
  }
  return {
    kindLabel: formatUnknownMachineCode(kind, language),
    summary: formatUnknownMachineCode(kind, language),
  };
}

export function formatPortfolioStressScenario(
  scenario: Pick<StressScenario, 'id' | 'name' | 'description'>,
  language: UiLanguage,
): { name: string; description: string } {
  const catalog = codes(language);
  const keys = SCENARIO_KEYS[scenario.id as keyof typeof SCENARIO_KEYS];
  if (keys) {
    return {
      name: catalog[keys[0]],
      description: catalog[keys[1]],
    };
  }
  return {
    name: formatUnknownMachineCode(scenario.id, language),
    description: scenario.description
      ? formatLabeledDiagnostic(scenario.description, language)
      : formatEmptyDisplay(),
  };
}

export { formatLabeledDiagnostic };
