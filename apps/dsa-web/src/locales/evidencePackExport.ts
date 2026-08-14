// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiLanguages';

type EvidencePackExportText = {
  exportAuditPackageZip: string;
  exportEvidenceChainJson: string;
  exportFailed: string;
  exportTruncated: string;
};

export const EVIDENCE_PACK_EXPORT_TEXT = {
    zh: {
      exportAuditPackageZip: '导出可审计报告包 (ZIP)',
      exportEvidenceChainJson: '导出证据链 JSON',
      exportFailed: '可审计报告包导出失败',
      exportTruncated: '导出内容已按服务端规则截断。详见包内 truncation / gaps 字段。',
    },
    'zh-TW': {
      exportAuditPackageZip: '匯出可稽核報告包 (ZIP)',
      exportEvidenceChainJson: '匯出證據鏈 JSON',
      exportFailed: '可稽核報告包匯出失敗',
      exportTruncated: '匯出內容已按伺服器規則截斷。詳見包內 truncation / gaps 欄位。',
    },
    en: {
      exportAuditPackageZip: 'Export audit package (ZIP)',
      exportEvidenceChainJson: 'Export evidence chain JSON',
      exportFailed: 'Audit package export failed',
      exportTruncated: 'Export was truncated by server rules. See truncation / gaps fields in the package.',
    },
    ja: {
      exportAuditPackageZip: '監査パッケージをエクスポート (ZIP)',
      exportEvidenceChainJson: '証拠チェーン JSON をエクスポート',
      exportFailed: '監査パッケージのエクスポートに失敗しました',
      exportTruncated: 'サーバールールによりエクスポートが切り詰められました。パッケージ内の truncation / gaps フィールドを確認してください。',
    },
    ko: {
      exportAuditPackageZip: '감사 패키지 내보내기 (ZIP)',
      exportEvidenceChainJson: '증거 체인 JSON 내보내기',
      exportFailed: '감사 패키지 내보내기 실패',
      exportTruncated: '서버 규칙에 따라 잘렸습니다. 패키지의 truncation / gaps 필드를 확인하세요.',
    },
    de: {
      exportAuditPackageZip: 'Audit-Paket exportieren (ZIP)',
      exportEvidenceChainJson: 'Beweiskette als JSON exportieren',
      exportFailed: 'Export des Audit-Pakets fehlgeschlagen',
      exportTruncated: 'Der Export wurde nach Serverregeln gekürzt. Details stehen in den Feldern truncation / gaps des Pakets.',
    },
    es: {
      exportAuditPackageZip: 'Exportar paquete de auditoría (ZIP)',
      exportEvidenceChainJson: 'Exportar cadena de evidencias JSON',
      exportFailed: 'Error al exportar el paquete de auditoría',
      exportTruncated: 'La exportación se truncó según las reglas del servidor. Consulte los campos truncation / gaps del paquete.',
    },
    ms: {
      exportAuditPackageZip: 'Eksport pakej audit (ZIP)',
      exportEvidenceChainJson: 'Eksport rantaian bukti JSON',
      exportFailed: 'Eksport pakej audit gagal',
      exportTruncated: 'Eksport dipotong mengikut peraturan pelayan. Lihat medan truncation / gaps dalam pakej.',
    },
    fr: {
      exportAuditPackageZip: 'Exporter le paquet d’audit (ZIP)',
      exportEvidenceChainJson: 'Exporter la chaîne de preuves JSON',
      exportFailed: 'Échec de l’export du paquet d’audit',
      exportTruncated: 'L’export a été tronqué selon les règles du serveur. Consultez les champs truncation / gaps du paquet.',
    },
    id: {
      exportAuditPackageZip: 'Ekspor paket audit (ZIP)',
      exportEvidenceChainJson: 'Ekspor rantai bukti JSON',
      exportFailed: 'Ekspor paket audit gagal',
      exportTruncated: 'Ekspor dipotong sesuai aturan server. Lihat kolom truncation / gaps dalam paket.',
    },
} satisfies Record<UiLanguage, EvidencePackExportText>;
