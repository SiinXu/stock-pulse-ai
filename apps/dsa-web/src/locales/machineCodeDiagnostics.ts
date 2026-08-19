// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  unknownCode: '未知编码（{code}）',
  unknownStatus: '未知状态 ({code})',
  diagnosticDetail: '诊断：{detail}',
} as const;

const en: Record<keyof typeof zh, string> = {
  unknownCode: 'Unknown code ({code})',
  unknownStatus: 'Unknown status ({code})',
  diagnosticDetail: 'Diagnostic: {detail}',
};

export const MACHINE_CODE_DIAGNOSTICS: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord(
  'locales.machineCodeDiagnostics.MACHINE_CODE_DIAGNOSTICS',
  { zh, en },
);
