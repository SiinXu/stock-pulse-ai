// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

export const REASONING_TRACE_EXPORT_TEXT = createUiLanguageRecord(
  'locales.reasoningTraceExport.REASONING_TRACE_EXPORT_TEXT',
  {
    zh: {
      exportReasoningTraceJson: '导出推理轨迹 JSON',
      exportReasoningTraceMarkdown: '导出推理轨迹 Markdown',
      exportReasoningTraceBusy: '正在导出推理轨迹…',
      exportReasoningTraceTruncated: '轨迹超过字符预算，已按服务端规则截断后下载。截断详情见导出包内的 truncation 字段。',
      exportReasoningTraceDisabled: '推理轨迹导出当前关闭。请在设置 → Agent 行为 → 执行中开启「推理轨迹导出」（REASONING_TRACE_EXPORT_ENABLED）。',
      exportReasoningTraceDisabledLink: '打开设置',
      exportReasoningTraceFailed: '推理轨迹导出失败',
      exportReasoningTraceHint: '默认关闭。导出内容经服务端脱敏，但仍属敏感运营数据。',
    },
    en: {
      exportReasoningTraceJson: 'Export reasoning trace JSON',
      exportReasoningTraceMarkdown: 'Export reasoning trace Markdown',
      exportReasoningTraceBusy: 'Exporting reasoning trace…',
      exportReasoningTraceTruncated: 'The trace exceeded the character budget and was truncated by the server. See the truncation field in the package.',
      exportReasoningTraceDisabled: 'Reasoning trace export is off. Enable Reasoning Trace Export (REASONING_TRACE_EXPORT_ENABLED) under Settings → Agent Behavior → Execution.',
      exportReasoningTraceDisabledLink: 'Open Settings',
      exportReasoningTraceFailed: 'Reasoning trace export failed',
      exportReasoningTraceHint: 'Off by default. Exports are server-redacted but remain sensitive operator data.',
    },
    ko: {
      exportReasoningTraceJson: '추론 트레이스 JSON 내보내기',
      exportReasoningTraceMarkdown: '추론 트레이스 Markdown 내보내기',
      exportReasoningTraceBusy: '추론 트레이스 내보내는 중…',
      exportReasoningTraceTruncated: '트레이스가 문자 예산을 초과하여 서버 규칙에 따라 잘린 뒤 다운로드되었습니다. 패키지의 truncation 필드를 확인하세요.',
      exportReasoningTraceDisabled: '추론 트레이스 내보내기가 꺼져 있습니다. 설정 → Agent 동작 → 실행에서 「추론 트레이스 내보내기」(REASONING_TRACE_EXPORT_ENABLED)를 켜세요.',
      exportReasoningTraceDisabledLink: '설정 열기',
      exportReasoningTraceFailed: '추론 트레이스 내보내기 실패',
      exportReasoningTraceHint: '기본값은 꺼짐입니다. 서버에서 마스킹되지만 여전히 민감한 운영 데이터입니다.',
    },
  },
);
