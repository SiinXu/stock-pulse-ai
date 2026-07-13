// Web-only settings Information Architecture (IA) mapping layer.
//
// The backend groups config under coarse `category` values (base, ai_model,
// data_source, notification, system, agent, backtest) with a few flat
// sub-categories. Phase 4 re-organizes the *Web* presentation into a stable
// two-level `section / view` structure WITHOUT touching backend categories,
// the Desktop client, or existing API consumers. This module is that mapping
// layer: it defines the section/view taxonomy and translates between the new
// `section/view` URLs and the legacy `category/sub` the panels still render.
//
// Labels are kept inline (bilingual) here — the same pattern the provider
// templates use — so the taxonomy is self-contained and testable. Navigation
// components read these labels via `sectionLabel` / `viewLabel`.

export type UiLang = 'zh' | 'en';

interface BilingualLabel {
  zh: string;
  en: string;
}

export type SettingsSectionId =
  | 'overview'
  | 'ai_models'
  | 'data_sources'
  | 'agent_behavior'
  | 'conversation'
  | 'reports'
  | 'alerts'
  | 'notifications'
  | 'backtesting'
  | 'system_security'
  | 'advanced';

export type AiModelsViewId =
  | 'overview'
  | 'connections'
  | 'task_routing'
  | 'reliability'
  | 'advanced';

export interface SettingsView {
  id: string;
  label: BilingualLabel;
}

export interface SettingsSection {
  id: SettingsSectionId;
  label: BilingualLabel;
  /** Ordered second-level views. A single implicit view uses `defaultView`. */
  views: SettingsView[];
  defaultView: string;
}

// First-level sections in display order. Only AI & Models is split into
// multiple second-level views in this phase; other sections carry a single
// implicit view (`main`) so the two-level shell renders uniformly.
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: 'overview',
    label: { zh: '概览', en: 'Overview' },
    views: [{ id: 'readiness', label: { zh: '就绪状态', en: 'Readiness' } }],
    defaultView: 'readiness',
  },
  {
    id: 'ai_models',
    label: { zh: 'AI 与模型', en: 'AI & Models' },
    views: [
      { id: 'overview', label: { zh: '总览', en: 'Overview' } },
      { id: 'connections', label: { zh: '连接', en: 'Connections' } },
      { id: 'task_routing', label: { zh: '任务路由', en: 'Task Routing' } },
      { id: 'reliability', label: { zh: '可靠性', en: 'Reliability' } },
      { id: 'advanced', label: { zh: '高级', en: 'Advanced' } },
    ],
    defaultView: 'connections',
  },
  {
    id: 'data_sources',
    label: { zh: '数据源', en: 'Data Sources' },
    views: [{ id: 'providers', label: { zh: '数据提供方', en: 'Providers' } }],
    defaultView: 'providers',
  },
  {
    id: 'agent_behavior',
    label: { zh: 'Agent 行为', en: 'Agent Behavior' },
    views: [{ id: 'execution', label: { zh: '执行', en: 'Execution' } }],
    defaultView: 'execution',
  },
  {
    id: 'conversation',
    label: { zh: '对话', en: 'Conversation' },
    views: [{ id: 'context', label: { zh: '上下文', en: 'Context' } }],
    defaultView: 'context',
  },
  {
    id: 'reports',
    label: { zh: '报告', en: 'Reports' },
    views: [{ id: 'output', label: { zh: '输出', en: 'Output' } }],
    defaultView: 'output',
  },
  {
    id: 'alerts',
    label: { zh: '告警与自动化', en: 'Alerts & Automation' },
    views: [{ id: 'rules', label: { zh: '规则', en: 'Rules' } }],
    defaultView: 'rules',
  },
  {
    id: 'notifications',
    label: { zh: '通知', en: 'Notifications' },
    views: [{ id: 'channels', label: { zh: '渠道', en: 'Channels' } }],
    defaultView: 'channels',
  },
  {
    id: 'backtesting',
    label: { zh: '回测', en: 'Backtesting' },
    views: [{ id: 'engine', label: { zh: '引擎', en: 'Engine' } }],
    defaultView: 'engine',
  },
  {
    id: 'system_security',
    label: { zh: '系统与安全', en: 'System & Security' },
    views: [{ id: 'runtime', label: { zh: '运行时', en: 'Runtime' } }],
    defaultView: 'runtime',
  },
  {
    id: 'advanced',
    label: { zh: '高级', en: 'Advanced' },
    views: [{ id: 'raw_config', label: { zh: '原始配置', en: 'Raw Config' } }],
    defaultView: 'raw_config',
  },
];

const SECTION_BY_ID = new Map(SETTINGS_SECTIONS.map((section) => [section.id, section]));

export function getSection(sectionId: string): SettingsSection | undefined {
  return SECTION_BY_ID.get(sectionId as SettingsSectionId);
}

export function isSettingsSectionId(value: string): value is SettingsSectionId {
  return SECTION_BY_ID.has(value as SettingsSectionId);
}

export function sectionLabel(sectionId: SettingsSectionId, language: UiLang): string {
  const label = SECTION_BY_ID.get(sectionId)?.label;
  return label ? label[language] : sectionId;
}

export function viewLabel(sectionId: SettingsSectionId, viewId: string, language: UiLang): string {
  const view = SECTION_BY_ID.get(sectionId)?.views.find((entry) => entry.id === viewId);
  return view ? view.label[language] : viewId;
}

export function getSectionViews(sectionId: SettingsSectionId): SettingsView[] {
  return SECTION_BY_ID.get(sectionId)?.views ?? [];
}

export function getDefaultView(sectionId: SettingsSectionId): string {
  return SECTION_BY_ID.get(sectionId)?.defaultView ?? '';
}

export interface SectionViewTarget {
  section: SettingsSectionId;
  view: string;
}

export interface LegacyTab {
  category: string;
  sub: string | null;
}

// Legacy (backend category, sub) -> new (section, view). Used to migrate old
// deep links / bookmarks to the new URL scheme, and to resolve which section a
// given backend key/panel belongs to.
export function legacyToSectionView(category: string, sub: string | null): SectionViewTarget {
  switch (category) {
    case 'base':
      return { section: 'overview', view: 'readiness' };
    case 'ai_model':
      if (sub === 'providers') {
        return { section: 'ai_models', view: 'advanced' };
      }
      return { section: 'ai_models', view: 'connections' };
    case 'data_source':
      return { section: 'data_sources', view: 'providers' };
    case 'notification':
      if (sub === 'rules') {
        return { section: 'alerts', view: 'rules' };
      }
      return { section: 'notifications', view: 'channels' };
    case 'agent':
      return { section: 'agent_behavior', view: 'execution' };
    case 'backtest':
      return { section: 'backtesting', view: 'engine' };
    case 'system':
      return { section: 'system_security', view: 'runtime' };
    default:
      return { section: 'overview', view: 'readiness' };
  }
}

// New (section, view) -> legacy (category, sub) so the existing category-based
// panels keep rendering under the new navigation while the field-level views
// (Task Routing / Reliability / Reports / Conversation) are built out in the
// following slices.
export function sectionViewToLegacy(section: string, view: string | null): LegacyTab {
  switch (section) {
    case 'overview':
      return { category: 'base', sub: null };
    case 'ai_models':
      return { category: 'ai_model', sub: view === 'advanced' ? 'providers' : 'model' };
    case 'data_sources':
      return { category: 'data_source', sub: 'providers' };
    case 'agent_behavior':
      return { category: 'agent', sub: null };
    case 'conversation':
      // Context/compression fields still live under the agent category until the
      // dedicated Conversation view is populated in a later slice.
      return { category: 'agent', sub: null };
    case 'reports':
      // Report output fields are split out of notification in a later slice; for
      // now the Reports section maps to the notification rules panel.
      return { category: 'notification', sub: 'rules' };
    case 'alerts':
      return { category: 'notification', sub: 'rules' };
    case 'notifications':
      return { category: 'notification', sub: 'channels' };
    case 'backtesting':
      return { category: 'backtest', sub: null };
    case 'system_security':
      return { category: 'system', sub: null };
    case 'advanced':
      return { category: 'ai_model', sub: 'providers' };
    default:
      return { category: 'base', sub: null };
  }
}

// Resolve a possibly-partial/unknown section+view pair to a valid target,
// falling back to the section default view (or the first section) so deep links
// and refreshes never land on an empty view.
export function normalizeSectionView(section: string | null, view: string | null): SectionViewTarget {
  const resolvedSection = section && isSettingsSectionId(section) ? section : SETTINGS_SECTIONS[0].id;
  const definition = SECTION_BY_ID.get(resolvedSection);
  const views = definition?.views ?? [];
  const resolvedView = view && views.some((entry) => entry.id === view)
    ? view
    : definition?.defaultView ?? views[0]?.id ?? '';
  return { section: resolvedSection, view: resolvedView };
}
