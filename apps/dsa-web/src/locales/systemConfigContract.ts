import type { UiLanguage } from '../i18n/uiText';
import type { ConfigContractDiagnostic } from '../utils/configConditions';
import type { SystemConfigPlacementDiagnostic } from '../utils/systemConfigSchemaCompatibility';

const zh = {
  missing_ai_ui_placement: '后端配置 Schema 缺少 AI 字段归属；该字段仅供诊断，暂时只读。',
  unknown_ui_placement: '当前客户端无法识别后端字段归属；该字段仅供诊断，暂时只读。',
  unknown_condition: '当前客户端无法解释字段条件契约；该字段保持可见但暂时只读。',
} as const;

const en: Record<keyof typeof zh, string> = {
  missing_ai_ui_placement: 'The backend schema is missing ownership for this AI field. It is read-only and shown for diagnostics.',
  unknown_ui_placement: 'This client does not recognize the backend field placement. It is read-only and shown for diagnostics.',
  unknown_condition: 'This client cannot interpret the field condition contract. The field remains visible but read-only.',
};

export const SYSTEM_CONFIG_CONTRACT_TEXT: Record<
  UiLanguage,
  Record<keyof typeof zh, string>
> = { zh, en };

export function getSystemConfigContractDiagnosticText(
  language: UiLanguage,
  diagnostic: SystemConfigPlacementDiagnostic | ConfigContractDiagnostic,
): string {
  return SYSTEM_CONFIG_CONTRACT_TEXT[language][diagnostic];
}
