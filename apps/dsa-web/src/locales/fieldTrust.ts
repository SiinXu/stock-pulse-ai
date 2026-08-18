// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  title: '字段可信度',
  description:
    '展示行情字段的来源、时滞、过期与跨源冲突。冲突会被标出，系统不会悄悄选定某一个来源当真值。',
  status: '状态',
  quoteSource: '行情来源',
  lag: '时滞（秒）',
  stale: '过期',
  confidence: '分析置信度',
  gaps: '缺口',
  providerHealth: '数据源健康',
  field: '字段',
  value: '取值',
  source: '来源',
  origin: '来源角色',
  staleness: '新鲜度',
  conflict: '冲突',
  yes: '是',
  no: '否',
  refresh: '刷新',
  refreshing: '刷新中…',
  loadFailed: '字段可信度请求失败',
  unavailableTitle: '行情可信度不可用',
  unavailableDescription: '所有数据源都未能返回行情；不会编造字段或选定单一真值。',
  degradedTitle: '行情可信度已降级',
  degradedDescription: '存在过期、冲突、未归因或数据源失败。请把冲突字段当作未决，而不是已确认报价。',
  emptyTitle: '暂无字段可信度',
  emptyDescription: '尚无可展示的字段级归因。',
  okTitle: '字段归因完整',
  disclaimer: '研究证据，非投资建议',
  notAvailable: '—',
  statusOk: '正常',
  statusDegraded: '已降级',
  statusUnavailable: '不可用',
  stalenessFresh: '新鲜',
  stalenessStale: '过期',
  stalenessUnknown: '未知',
  originPrimary: '主源',
  originSupplement: '补充',
  originUnknown: '未知',
  confidenceHigh: '高',
  confidenceMedium: '中',
  confidenceLow: '低',
  healthOk: '可用',
  healthFailed: '失败',
  healthEmpty: '空响应',
  healthUnavailable: '不可用',
  rolePrimary: '主源',
  roleSupplement: '补充',
  roleAttempted: '已尝试',
  conflictValues: '冲突取值（均保留，未选定真值）',
  gapConflict: '数据源对该字段意见不一致，系统未选定真值。',
  gapStale: '该字段的数据源时间已超过实时有效期。',
  gapUnattributed: '该字段缺少数据源归因，不能当作已验证。',
  gapUnknownStaleness: '无法证明该字段新鲜，不能当作实时数据。',
  gapMissing: '行情将此字段标记为缺失。',
  gapConflictCheckSkipped: '跨源比对未完成，不能当作已达成一致。',
  gapProviderFailed: '数据源尝试失败：{detail}',
  gapProviderUnavailable: '数据源不可用：{detail}',
  gapNoAttributableFields: '没有可归因的覆盖字段。',
  gapMetadataAbsent: '行情未携带字段级可信度元数据。',
  gapQuoteUnavailable: '所有数据源都未能返回实时行情。',
  gapUnknown: '未分类缺口（{code}）',
} as const;

const en = {
  title: 'Field trust',
  description:
    'Per-field source, lag, staleness, and cross-provider conflicts. Conflicts stay visible — no source is silently chosen as truth.',
  status: 'Status',
  quoteSource: 'Quote source',
  lag: 'Lag (seconds)',
  stale: 'Stale',
  confidence: 'Analysis confidence',
  gaps: 'Gaps',
  providerHealth: 'Provider health',
  field: 'Field',
  value: 'Value',
  source: 'Source',
  origin: 'Origin',
  staleness: 'Freshness',
  conflict: 'Conflict',
  yes: 'Yes',
  no: 'No',
  refresh: 'Refresh',
  refreshing: 'Refreshing…',
  loadFailed: 'Field-trust request failed',
  unavailableTitle: 'Quote trust unavailable',
  unavailableDescription:
    'No provider returned a quote. Missing fields are never invented and no single source is treated as truth.',
  degradedTitle: 'Quote trust degraded',
  degradedDescription:
    'Stale, conflicting, unattributed, or failed-provider fields are present. Treat conflicts as unresolved, not as a confirmed quote.',
  emptyTitle: 'No field-trust rows',
  emptyDescription: 'No attributable quote fields are available yet.',
  okTitle: 'Field attribution complete',
  disclaimer: 'Research evidence only — not investment advice',
  notAvailable: '—',
  statusOk: 'OK',
  statusDegraded: 'Degraded',
  statusUnavailable: 'Unavailable',
  stalenessFresh: 'Fresh',
  stalenessStale: 'Stale',
  stalenessUnknown: 'Unknown',
  originPrimary: 'Primary',
  originSupplement: 'Supplement',
  originUnknown: 'Unknown',
  confidenceHigh: 'High',
  confidenceMedium: 'Medium',
  confidenceLow: 'Low',
  healthOk: 'OK',
  healthFailed: 'Failed',
  healthEmpty: 'Empty',
  healthUnavailable: 'Unavailable',
  rolePrimary: 'Primary',
  roleSupplement: 'Supplement',
  roleAttempted: 'Attempted',
  conflictValues: 'Conflict values (kept; no source chosen as truth)',
  gapConflict: 'Providers disagreed; no source was chosen as truth.',
  gapStale: 'Provider timestamp exceeded the realtime TTL.',
  gapUnattributed: 'Field has no provider attribution and must not be treated as verified.',
  gapUnknownStaleness: 'Staleness could not be proven; do not treat as fresh.',
  gapMissing: 'The quote reported this field as missing.',
  gapConflictCheckSkipped: 'Cross-source comparison did not finish; do not treat as agreement.',
  gapProviderFailed: 'Provider attempt failed: {detail}',
  gapProviderUnavailable: 'Provider unavailable: {detail}',
  gapNoAttributableFields: 'No covered quote fields were attributable.',
  gapMetadataAbsent: 'Quote carried no field-level trust metadata.',
  gapQuoteUnavailable: 'No realtime quote available from any provider.',
  gapUnknown: 'Unclassified gap ({code})',
} as const;

export type FieldTrustText = { readonly [Key in keyof typeof en]: string };

const GAP_TEXT_BY_CODE: Record<string, keyof FieldTrustText> = {
  conflict: 'gapConflict',
  stale: 'gapStale',
  unattributed: 'gapUnattributed',
  unknown_staleness: 'gapUnknownStaleness',
  missing: 'gapMissing',
  conflict_check_skipped: 'gapConflictCheckSkipped',
  provider_failed: 'gapProviderFailed',
  provider_unavailable: 'gapProviderUnavailable',
  no_attributable_fields: 'gapNoAttributableFields',
  metadata_absent: 'gapMetadataAbsent',
  quote_unavailable: 'gapQuoteUnavailable',
};

/** Bilingual copy for the field-trust panel (zh source + en; other UI langs fall back to en). */
export const FIELD_TRUST_TEXT: Record<UiLanguage, FieldTrustText> = {
  zh,
  en,
  'zh-TW': zh,
  ja: en,
  ko: en,
  de: en,
  es: en,
  ms: en,
  fr: en,
  id: en,
};

const formatFieldTrustTemplate = (template: string, params: Record<string, string>): string =>
  template.replace(/\{([A-Za-z0-9_]+)\}/g, (_match, key: string) => params[key] ?? '');

export const fieldTrustStatusMessage = (
  text: FieldTrustText,
  status: 'ok' | 'degraded' | 'unavailable',
): string => {
  if (status === 'ok') return text.okTitle;
  if (status === 'degraded') return text.degradedDescription;
  return text.unavailableDescription;
};

export const fieldTrustGapMessage = (
  text: FieldTrustText,
  gap: { code: string; field?: string | null; detail?: string | null },
): string => {
  const key = GAP_TEXT_BY_CODE[gap.code];
  if (!key) {
    return formatFieldTrustTemplate(text.gapUnknown, { code: gap.code });
  }
  return formatFieldTrustTemplate(text[key], {
    code: gap.code,
    detail: gap.detail || gap.code,
    field: gap.field || '',
  });
};
