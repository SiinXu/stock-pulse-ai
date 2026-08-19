// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import { getPersonalPerformanceReasonLabels } from '../../locales/personalPerformanceReasons';
import { PORTFOLIO_SIDE_LABELS } from '../../locales/portfolio';
import type { PortfolioSide } from '../../types/portfolio';
import {
  formatEmptyDisplay,
  formatUnknownMachineCode,
} from './unknownCode';

const KNOWN_SIDES = new Set<PortfolioSide>(['buy', 'sell']);

export function formatPaperDecisionSide(
  side: string | null | undefined,
  language: UiLanguage,
): string {
  if (side == null || side === '') return formatEmptyDisplay();
  const normalized = side.trim().toLowerCase();
  if (KNOWN_SIDES.has(normalized as PortfolioSide)) {
    return PORTFOLIO_SIDE_LABELS[language][normalized as PortfolioSide];
  }
  return formatUnknownMachineCode(normalized, language);
}

export function formatPaperDecisionReason(
  reason: { code?: string | null; message?: string | null },
  language: UiLanguage,
): string {
  const catalog = getPersonalPerformanceReasonLabels(language);
  const code = String(reason.code ?? '').trim();
  if (!code) return formatEmptyDisplay();
  const label = catalog[code as keyof typeof catalog];
  if (label) return label;
  return formatUnknownMachineCode(code, language);
}
