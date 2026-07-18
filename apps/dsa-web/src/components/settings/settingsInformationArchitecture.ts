// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../../i18n/uiLanguages';
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

// First-level sections in display order. Sections with multiple workflows use
// second-level views; the rest carry a single implicit view.
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: 'overview',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.overview.label", { zh: '概览', en: 'Overview' }),
    views: [{ id: 'readiness', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.overview.views.readiness.label", { zh: '就绪状态', en: 'Readiness' }) }],
    defaultView: 'readiness',
  },
  {
    id: 'ai_models',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.label", { zh: 'AI 与模型', en: 'AI & Models' }),
    views: [
      { id: 'overview', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.overview.label", { zh: '总览', en: 'Overview' }) },
      { id: 'connections', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.connections.label", { zh: '模型接入', en: 'Model Access' }) },
      { id: 'task_routing', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.task_routing.label", { zh: '任务路由', en: 'Task Routing' }) },
      { id: 'reliability', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.ai_models.views.reliability.label", { zh: '可靠性', en: 'Reliability' }) },
    ],
    defaultView: 'connections',
  },
  {
    id: 'data_sources',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.label", { zh: '数据源', en: 'Data Sources' }),
    views: [
      { id: 'sources', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.data_sources.views.sources.label", { zh: '行情与资讯', en: 'Sources' }) },
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
    views: [{ id: 'rules', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.alerts.views.rules.label", { zh: '规则', en: 'Rules' }) }],
    defaultView: 'rules',
  },
  {
    id: 'notifications',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.notifications.label", { zh: '通知', en: 'Notifications' }),
    views: [{ id: 'channels', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.notifications.views.channels.label", { zh: '渠道', en: 'Channels' }) }],
    defaultView: 'channels',
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
    views: [{ id: 'runtime', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.system_security.views.runtime.label", { zh: '运行时', en: 'Runtime' }) }],
    defaultView: 'runtime',
  },
  {
    id: 'advanced',
    label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.label", { zh: '高级', en: 'Advanced' }),
    views: [
      { id: 'raw_config', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.views.raw_config.label", { zh: '原始配置', en: 'Raw Config' }) },
      { id: 'diagnostics', label: createUiLanguageRecord("components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.advanced.views.diagnostics.label", { zh: '开发者诊断', en: 'Developer Diagnostics' }) },
    ],
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
      // Model Access (Connections) is the single entry for provider
      // credentials; the retired `providers` sub also lands here.
      return { section: 'ai_models', view: 'connections' };
    case 'data_source':
      return { section: 'data_sources', view: sub === 'providers' ? 'providers' : 'sources' };
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
