import type { UiLanguage } from '../i18n/uiText';

const zh = {
  eyebrow: '运行诊断', title: '运行状态', loading: '诊断加载中...', unavailable: '运行诊断暂不可用', noComponents: '暂无组件诊断', components: '关键链路', advanced: '高级字段', copy: '复制', copyDiagnostics: '复制排障信息', copied: '已复制', scope: '抓取 / LLM / 保存 / 通知链路', trace: 'Trace', task: 'Task', query: 'Query', trigger: '触发来源',
  fullReport: '完整分析报告', loadingReport: '加载报告中...', loadReportFailed: '加载报告失败', copyMarkdownSource: '复制 Markdown 源码', copyPlainText: '复制纯文本', close: '关闭', openLink: '跳转', loadingNews: '加载资讯中...', noNews: '暂无相关资讯', noNewsDescription: '可稍后刷新以获取最新资讯。',
  transparency: '透明度', traceability: '数据追溯', rawResult: '原始分析结果', analysisSnapshot: '分析快照', recordId: '记录 ID',
  overall: { normal: '正常', degraded: '部分降级', failed: '失败', unknown: '未知' },
  component: { ok: '正常', degraded: '最近失败后已降级', failed: '失败', unknown: '未知', not_configured: '未配置', skipped: '已跳过' },
  componentName: { realtime_quote: '实时行情', daily_data: '日线数据', news: '新闻', llm: '模型分析', notification: '通知', history: '历史记录' },
} as const;

const en = {
  eyebrow: 'RUN DIAGNOSTICS', title: 'Run Status', loading: 'Loading diagnostics...', unavailable: 'Diagnostics unavailable', noComponents: 'No component diagnostics', components: 'Key Path', advanced: 'Advanced Fields', copy: 'Copy', copyDiagnostics: 'Copy diagnostics', copied: 'Copied', scope: 'Fetch / LLM / save / notification path', trace: 'Trace', task: 'Task', query: 'Query', trigger: 'Trigger',
  fullReport: 'Full Analysis Report', loadingReport: 'Loading report...', loadReportFailed: 'Failed to load report', copyMarkdownSource: 'Copy Markdown Source', copyPlainText: 'Copy Plain Text', close: 'Close', openLink: 'Open', loadingNews: 'Loading news...', noNews: 'No related news', noNewsDescription: 'Refresh later to check for the latest updates.',
  transparency: 'TRANSPARENCY', traceability: 'Data Traceability', rawResult: 'Raw Analysis Result', analysisSnapshot: 'Analysis Snapshot', recordId: 'Record ID',
  overall: { normal: 'Normal', degraded: 'Degraded', failed: 'Failed', unknown: 'Unknown' },
  component: { ok: 'Normal', degraded: 'Recent failure', failed: 'Failed', unknown: 'Unknown', not_configured: 'Not configured', skipped: 'Skipped' },
  componentName: { realtime_quote: 'Real-time quote', daily_data: 'Daily data', news: 'News', llm: 'Model analysis', notification: 'Notification', history: 'History' },
} as const;

export const REPORT_CHROME_TEXT: Record<UiLanguage, typeof zh | typeof en> = { zh, en };
