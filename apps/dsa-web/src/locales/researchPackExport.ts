// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
export const RESEARCH_PACK_EXPORT_TEXT = createUiLanguageRecord('locales.researchPackExport.RESEARCH_PACK_EXPORT_TEXT', {
  zh: {
    exportResearchPack: '导出研报资产包', exportResearchPackBusy: '正在组装研报资产包…',
    exportResearchPackProgress: '组装进度',
    exportResearchPackTruncated: '资产包超过大小预算，已按服务端规则截断。详见包内 meta.json。',
    exportResearchPackDisabled: '研报资产包导出当前关闭。请在设置 → Agent 行为 → 执行中开启「研报资产包导出」（RESEARCH_PACK_EXPORT_ENABLED）。',
    exportResearchPackDisabledLink: '打开设置', exportResearchPackFailed: '研报资产包导出失败',
    exportResearchPackHint: '默认关闭。一键导出报告、决策卡、证据引用与脱敏轨迹；仍属敏感运营数据。',
  },
  en: {
    exportResearchPack: 'Export research pack', exportResearchPackBusy: 'Assembling research pack…',
    exportResearchPackProgress: 'Assembly progress',
    exportResearchPackTruncated: 'The pack exceeded the size budget and was truncated by the server. See meta.json.',
    exportResearchPackDisabled: 'Research pack export is off. Enable Research Pack Export (RESEARCH_PACK_EXPORT_ENABLED) under Settings → Agent Behavior → Execution.',
    exportResearchPackDisabledLink: 'Open Settings', exportResearchPackFailed: 'Research pack export failed',
    exportResearchPackHint: 'Off by default. One-click ZIP with report, decision card, evidence refs, and redacted trace.',
  },
  ko: {
    exportResearchPack: '리서치 팩 내보내기', exportResearchPackBusy: '리서치 팩 구성 중…',
    exportResearchPackProgress: '구성 진행',
    exportResearchPackTruncated: '팩이 크기 예산을 초과하여 잘렸습니다. meta.json을 확인하세요.',
    exportResearchPackDisabled: '리서치 팩 내보내기가 꺼져 있습니다. 설정 → Agent 동작 → 실행에서 켜세요.',
    exportResearchPackDisabledLink: '설정 열기', exportResearchPackFailed: '리서치 팩 내보내기 실패',
    exportResearchPackHint: '기본값은 꺼짐입니다. 보고서·결정 카드·증거 참조·마스킹 트레이스를 한 번에 내보냅니다.',
  },
});
