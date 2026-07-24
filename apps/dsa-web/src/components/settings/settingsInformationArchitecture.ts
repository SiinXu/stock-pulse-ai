// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../../i18n/uiLanguages';
import { SETTINGS_SECTION_IDS, SETTINGS_VIEW_IDS } from '../../routing/routes';
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
// Localized labels stay inline so the taxonomy remains self-contained and
// testable. Navigation components read them via `sectionLabel` / `viewLabel`.

export type UiLang = UiLanguage;

type LocalizedLabel = Record<UiLanguage, string>;

export type SettingsSectionId =
  | 'overview'
  | 'ai_models'
  | 'data_sources'
  | 'agent_behavior'
  | 'conversation'
  | 'reports'
  | 'alerts'
  | 'notifications'
  | typeof SETTINGS_SECTION_IDS.usage
  | 'backtesting'
  | 'system_security'
  | 'advanced';

export interface SettingsView {
  id: string;
  label: LocalizedLabel;
}

export interface SettingsSection {
  id: SettingsSectionId;
  label: LocalizedLabel;
  /** Ordered second-level views. A single implicit view uses `defaultView`. */
  views: SettingsView[];
  defaultView: string;
}

// First-level sections in display order. Content-heavy sections (AI & Models,
// Data Sources, Alerts & Automation, System & Security) split into multiple
// second-level views rendered as horizontal tabs; the rest carry a single
// implicit view so the two-level shell renders uniformly.
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: 'overview',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.overview.label", { zh: '概览', en: 'Overview' }),
    views: [{ id: 'readiness', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.overview.views.readiness.label", { zh: '就绪状态', en: 'Readiness' }) }],
    defaultView: 'readiness',
  },
  {
    id: SETTINGS_SECTION_IDS.aiModels,
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.label", { zh: 'AI 与模型', en: 'AI & Models' }),
    views: [
      { id: SETTINGS_VIEW_IDS.aiModels.overview, label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.overview.label", { zh: '总览', en: 'Overview' }) },
      { id: SETTINGS_VIEW_IDS.aiModels.connections, label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.connections.label", { zh: '模型接入', en: 'Model Access' }) },
      { id: SETTINGS_VIEW_IDS.aiModels.localModels, label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.local_models.label", { zh: '本地模型', en: 'Local Models' }) },
      { id: SETTINGS_VIEW_IDS.aiModels.taskRouting, label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.task_routing.label", { zh: '任务路由', en: 'Task Routing' }) },
      { id: SETTINGS_VIEW_IDS.aiModels.reliability, label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.reliability.label", { zh: '可靠性', en: 'Reliability' }) },
    ],
    defaultView: SETTINGS_VIEW_IDS.aiModels.connections,
  },
  {
    id: 'data_sources',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.label", { zh: '数据源', en: 'Data Sources' }),
    views: [
      { id: 'sources', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.views.sources.label", { zh: '行情与资讯', en: 'Sources' }) },
      { id: 'intelligence', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.views.intelligence.label", { zh: '情报源', en: 'Intel Sources' }) },
      { id: 'providers', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.views.providers.label", { zh: '数据提供方', en: 'Providers' }) },
    ],
    defaultView: 'sources',
  },
  {
    id: 'agent_behavior',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.agent_behavior.label", { zh: 'Agent 行为', en: 'Agent Behavior' }),
    views: [{ id: 'execution', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.agent_behavior.views.execution.label", { zh: '执行', en: 'Execution' }) }],
    defaultView: 'execution',
  },
  {
    id: 'conversation',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.conversation.label", { zh: '对话', en: 'Conversation' }),
    views: [{ id: 'context', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.conversation.views.context.label", { zh: '上下文', en: 'Context' }) }],
    defaultView: 'context',
  },
  {
    id: 'reports',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.reports.label", { zh: '报告', en: 'Reports' }),
    views: [{ id: 'output', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.reports.views.output.label", { zh: '输出', en: 'Output' }) }],
    defaultView: 'output',
  },
  {
    id: 'alerts',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.alerts.label", { zh: '告警与自动化', en: 'Alerts & Automation' }),
    views: [
      { id: 'routing', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.alerts.views.routing.label", { zh: '推送路由', en: 'Push Routing' }) },
      { id: 'behavior', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.alerts.views.behavior.label", { zh: '行为与频控', en: 'Behavior & Limits' }) },
      { id: 'events', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.alerts.views.events.label", { zh: '事件监控', en: 'Event Monitor' }) },
    ],
    defaultView: 'routing',
  },
  {
    id: 'notifications',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.notifications.label", { zh: '通知', en: 'Notifications' }),
    views: [{ id: 'channels', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.notifications.views.channels.label", { zh: '渠道', en: 'Channels' }) }],
    defaultView: 'channels',
  },
  {
    id: SETTINGS_SECTION_IDS.usage,
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.usage.label", { zh: '用量与成本', en: 'Usage & cost' }),
    // TokenUsagePage owns its period segments, so this section has no second-level settings view.
    views: [],
    defaultView: '',
  },
  {
    id: 'backtesting',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.backtesting.label", { zh: '回测', en: 'Backtesting' }),
    views: [{ id: 'engine', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.backtesting.views.engine.label", { zh: '引擎', en: 'Engine' }) }],
    defaultView: 'engine',
  },
  {
    id: 'system_security',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.label", { zh: '系统与安全', en: 'System & Security' }),
    views: [
      // Keeps the historical `runtime` id for URL back-compat; the tab hosts the
      // scheduler card, while plain system fields live on the General tab.
      { id: 'runtime', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.runtime.label", { zh: '调度', en: 'Scheduling' }) },
      { id: 'general', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.general.label", { zh: '系统设置', en: 'System Settings' }) },
      { id: 'service', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.service.label", { zh: '服务与日志', en: 'Web & Logs' }) },
      { id: 'security', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.security.label", { zh: '认证与安全', en: 'Auth & Security' }) },
      { id: 'about', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.about.label", { zh: '版本与更新', en: 'Version & Updates' }) },
    ],
    defaultView: 'runtime',
  },
  {
    id: 'advanced',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.label", { zh: '高级', en: 'Advanced' }),
    views: [
      // Keeps the historical `raw_config` id for URL back-compat; the tab now
      // reads as Backend Status since developer fields moved to `diagnostics`.
      { id: 'raw_config', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.views.raw_config.label", { zh: '后端状态', en: 'Backend Status' }) },
      { id: 'diagnostics', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.views.diagnostics.label", { zh: '开发者诊断', en: 'Developer Diagnostics' }) },
      { id: 'backup', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.views.backup.label", { zh: '配置备份', en: 'Config Backup' }) },
    ],
    defaultView: 'raw_config',
  },
];

// Sections a first-time user needs to reach a runnable setup. Beginner mode
// shows only these plus the currently-active section; everything else stays one
// click away behind an explicit "show advanced" reveal. This is presentation
// only — every section remains reachable by deep link and by revealing advanced.
export const BEGINNER_ESSENTIAL_SECTION_IDS: ReadonlySet<SettingsSectionId> = new Set<SettingsSectionId>([
  'overview',
  'ai_models',
  'data_sources',
  'notifications',
]);

export function isBeginnerEssentialSection(sectionId: SettingsSectionId): boolean {
  return BEGINNER_ESSENTIAL_SECTION_IDS.has(sectionId);
}

// The sections shown in the navigation for the current mode. In beginner mode
// with advanced hidden, only essentials plus the active section are listed so
// the user never loses the page they are on.
export function getVisibleSections(
  beginnerMode: boolean,
  advancedRevealed: boolean,
  activeSection: SettingsSectionId,
): SettingsSection[] {
  if (!beginnerMode || advancedRevealed) {
    return SETTINGS_SECTIONS;
  }
  return SETTINGS_SECTIONS.filter(
    (section) => isBeginnerEssentialSection(section.id) || section.id === activeSection,
  );
}

// Whether any advanced (non-essential) sections are currently hidden, i.e. the
// "show advanced" reveal should be offered.
export function hasHiddenAdvancedSections(
  beginnerMode: boolean,
  advancedRevealed: boolean,
): boolean {
  if (!beginnerMode || advancedRevealed) {
    return false;
  }
  return SETTINGS_SECTIONS.some((section) => !isBeginnerEssentialSection(section.id));
}

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
      // Model Access (Connections) is the single entry for provider
      // credentials; the retired `providers` sub also lands here.
      return { section: 'ai_models', view: 'connections' };
    case 'data_source':
      return { section: 'data_sources', view: sub === 'providers' ? 'providers' : 'sources' };
    case 'notification':
      if (sub === 'rules') {
        return { section: 'alerts', view: 'routing' };
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
      return { category: 'ai_model', sub: null };
    case 'data_sources':
      return { category: 'data_source', sub: view === 'providers' ? 'providers' : 'source' };
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
    case SETTINGS_SECTION_IDS.usage:
      // SettingsPage renders TokenUsagePage directly for this section.
      return { category: 'base', sub: null };
    case 'backtesting':
      return { category: 'backtest', sub: null };
    case 'system_security':
      return { category: 'system', sub: null };
    case 'advanced':
      // The top-level Advanced section renders its own aggregated card (keys
      // routed via the placement map); the legacy category only decides which
      // backend items load, and must not trigger another category's side cards.
      return { category: 'ai_model', sub: null };
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
