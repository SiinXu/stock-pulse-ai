// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { MACHINE_CODE_DIAGNOSTICS } from '../../locales/machineCodeDiagnostics';
import {
  formatEmptyDisplay,
  sanitizeDiagnosticText,
  sanitizeMachineCode,
} from './sanitizeDiagnostic';

export {
  STABLE_MACHINE_CODE,
  formatEmptyDisplay,
  isStableMachineCode,
  sanitizeDiagnosticText,
  sanitizeMachineCode,
  sanitizeUserAuthoredText,
} from './sanitizeDiagnostic';

export function formatUnknownMachineCode(
  code: string | null | undefined,
  language: UiLanguage,
): string {
  return formatUiText(MACHINE_CODE_DIAGNOSTICS[language].unknownCode, {
    code: sanitizeMachineCode(code),
  });
}

export function formatUnknownStatusCode(
  code: string | null | undefined,
  language: UiLanguage,
): string {
  return formatUiText(MACHINE_CODE_DIAGNOSTICS[language].unknownStatus, {
    code: sanitizeMachineCode(code),
  });
}

export function formatLabeledDiagnostic(
  detail: string | null | undefined,
  language: UiLanguage,
): string {
  const text = MACHINE_CODE_DIAGNOSTICS[language];
  if (detail == null || String(detail).trim() === '') return formatEmptyDisplay();
  return formatUiText(text.diagnosticDetail, {
    detail: sanitizeDiagnosticText(String(detail)),
  });
}
