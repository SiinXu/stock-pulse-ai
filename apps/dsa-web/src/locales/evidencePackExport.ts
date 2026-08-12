// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

export const EVIDENCE_PACK_EXPORT_TEXT = createUiLanguageRecord(
  'locales.evidencePackExport.EVIDENCE_PACK_EXPORT_TEXT',
  {
    zh: {
      exportAuditPackageZip: '导出可审计报告包 (ZIP)',
      exportEvidenceChainJson: '导出证据链 JSON',
      exportBusy: '正在导出…',
      exportDisabled: '可审计报告包导出当前关闭。请在设置 → Agent 行为 → 执行中开启「可审计报告包导出」（AUDIT_EXPORT_ENABLED）。',
      exportDisabledLink: '打开设置',
      exportFailed: '可审计报告包导出失败',
      exportHint: '导出包含报告、证据链、推理轨迹与显式缺口清单；服务端脱敏，但仍属敏感运营数据。默认关闭。',
      exportTruncated: '导出内容已按服务端规则截断。详见包内 truncation / gaps 字段。',
    },
    en: {
      exportAuditPackageZip: 'Export audit package (ZIP)',
      exportEvidenceChainJson: 'Export evidence chain JSON',
      exportBusy: 'Exporting…',
      exportDisabled: 'Audit package export is off. Enable Audit Package Export (AUDIT_EXPORT_ENABLED) under Settings → Agent Behavior → Execution.',
      exportDisabledLink: 'Open Settings',
      exportFailed: 'Audit package export failed',
      exportHint: 'Package includes report, evidence chain, reasoning trace, and explicit gaps. Server-redacted but still sensitive. Off by default.',
      exportTruncated: 'Export was truncated by server rules. See truncation / gaps fields in the package.',
    },
    ko: {
      exportAuditPackageZip: '감사 패키지 내보내기 (ZIP)',
      exportEvidenceChainJson: '증거 체인 JSON 내보내기',
      exportBusy: '내보내는 중…',
      exportDisabled: '감사 패키지 내보내기가 꺼져 있습니다. 설정 → Agent 동작 → 실행에서 AUDIT_EXPORT_ENABLED를 켜세요.',
      exportDisabledLink: '설정 열기',
      exportFailed: '감사 패키지 내보내기 실패',
      exportHint: '보고서, 증거 체인, 추론 트레이스, 명시적 공백 목록을 포함합니다. 서버에서 마스킹되지만 민감한 운영 데이터입니다.',
      exportTruncated: '서버 규칙에 따라 잘렸습니다. 패키지의 truncation / gaps 필드를 확인하세요.',
    },
  },
);
