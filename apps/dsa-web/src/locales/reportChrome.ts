import type { ReportLanguage } from '../types/analysis';

const zh = {
  eyebrow: '运行诊断', title: '运行状态', loading: '诊断加载中...', unavailable: '运行诊断暂不可用', noComponents: '暂无组件诊断', components: '关键链路', advanced: '高级字段', copy: '复制排障信息', copied: '已复制', scope: '抓取 / LLM / 保存 / 通知链路', trace: 'Trace', task: 'Task', query: 'Query', trigger: '触发来源',
  overall: { normal: '正常', degraded: '部分降级', failed: '失败', unknown: '未知' },
  component: { ok: '正常', degraded: '最近失败后已降级', failed: '失败', unknown: '未知', not_configured: '未配置', skipped: '已跳过' },
} as const;

const en = {
  eyebrow: 'RUN DIAGNOSTICS', title: 'Run Status', loading: 'Loading diagnostics...', unavailable: 'Diagnostics unavailable', noComponents: 'No component diagnostics', components: 'Key Path', advanced: 'Advanced Fields', copy: 'Copy diagnostics', copied: 'Copied', scope: 'Fetch / LLM / save / notification path', trace: 'Trace', task: 'Task', query: 'Query', trigger: 'Trigger',
  overall: { normal: 'Normal', degraded: 'Degraded', failed: 'Failed', unknown: 'Unknown' },
  component: { ok: 'Normal', degraded: 'Recent failure', failed: 'Failed', unknown: 'Unknown', not_configured: 'Not configured', skipped: 'Skipped' },
} as const;

const ko = {
  eyebrow: '실행 진단', title: '실행 상태', loading: '진단 불러오는 중...', unavailable: '실행 진단을 사용할 수 없음', noComponents: '컴포넌트 진단 없음', components: '핵심 경로', advanced: '고급 필드', copy: '진단 정보 복사', copied: '복사됨', scope: '수집 / LLM / 저장 / 알림 경로', trace: 'Trace', task: 'Task', query: 'Query', trigger: '트리거',
  overall: { normal: '정상', degraded: '부분 강등', failed: '실패', unknown: '알 수 없음' },
  component: { ok: '정상', degraded: '최근 실패 후 강등', failed: '실패', unknown: '알 수 없음', not_configured: '미설정', skipped: '건너뜀' },
} as const;

export const REPORT_CHROME_TEXT: Record<ReportLanguage, typeof zh | typeof en | typeof ko> = { zh, en, ko };
