// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Source-language copy registered by the stable API error catalog. */
export const EVIDENCE_EXPORT_ERROR_SOURCES = {
  audit_export_disabled: {
    zh: { title: '审计导出关闭', message: '请在设置中启用。' },
    en: { title: 'Audit disabled', message: 'Enable in Settings.' },
  },
  evidence_chain_disabled: {
    zh: { title: '证据链关闭', message: '请在设置中启用。' },
    en: { title: 'Evidence disabled', message: 'Enable in Settings.' },
  },
  evidence_chain_auth_required: {
    zh: { title: '需管理员认证', message: '请启用并登录。' },
    en: { title: 'Admin auth required', message: 'Enable. Sign in.' },
  },
  audit_export_auth_required: {
    zh: { title: '需管理员认证', message: '请启用并登录。' },
    en: { title: 'Admin auth required', message: 'Enable. Sign in.' },
  },
} as const;
