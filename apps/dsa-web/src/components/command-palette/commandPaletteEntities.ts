// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  AGENT_SETUP_COPY,
  AGENT_SETUP_PRESETS,
  type AgentSetupPresetId,
} from '../settings/agentSetupPresets';
import {
  SETTINGS_SECTIONS,
  type SettingsSectionId,
} from '../settings/settingsInformationArchitecture';
import type { SkillInfo } from '../../api/agent';
import type { UiLanguage } from '../../i18n/uiLanguages';
import {
  APP_ROUTE_PATHS,
  buildSettingsHref,
} from '../../routing/routes';
import {
  DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
  setResearchDiscoverRouteState,
} from '../../routing/researchRouteState';
import { getStrategyDisplay } from '../../utils/strategyDisplay';
import { COMMAND_PALETTE_RESULT_LIMIT } from './useCommandPaletteSearch';

export type CommandPaletteEntity = {
  id: string;
  href: string;
  label: string;
  description?: string;
  meta?: string;
  /** Lowercased fields used for substring matching. */
  searchText: string;
};

function includesQuery(haystack: string, query: string): boolean {
  return query.length === 0 || haystack.includes(query);
}

const SETTINGS_VIEW_SEARCH_ALIASES: Readonly<Record<string, string>> = {
  'ai_models/connections': 'cloud model cloud api api model provider model service 云端模型 云模型 api 模型 模型服务 服务商',
};

function takeLimited(items: CommandPaletteEntity[], limit = COMMAND_PALETTE_RESULT_LIMIT): CommandPaletteEntity[] {
  return items.slice(0, limit);
}

/** Canonical Discover deep link for a strategy / skill id. */
export function buildDiscoverStrategyHref(strategyId: string): string {
  const search = setResearchDiscoverRouteState(new URLSearchParams(), {
    ...DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
    strategy: strategyId,
  }).toString();
  return search
    ? `${APP_ROUTE_PATHS.researchDiscover}?${search}`
    : APP_ROUTE_PATHS.researchDiscover;
}

export function buildSkillEntities(
  skills: readonly SkillInfo[],
  language: UiLanguage,
  query: string,
  limit = COMMAND_PALETTE_RESULT_LIMIT,
): CommandPaletteEntity[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (normalizedQuery.length === 0) return [];

  const matches: CommandPaletteEntity[] = [];
  for (const skill of skills) {
    const display = getStrategyDisplay(skill, language);
    const searchText = [
      skill.id,
      skill.name,
      skill.description,
      display.name,
      display.description,
      display.category,
    ].join(' ').toLocaleLowerCase();
    if (!includesQuery(searchText, normalizedQuery)) continue;
    matches.push({
      id: `skill-${skill.id}`,
      href: buildDiscoverStrategyHref(skill.id),
      label: display.name,
      description: display.description || skill.description || undefined,
      meta: display.category || skill.id,
      searchText,
    });
  }
  return takeLimited(matches, limit);
}

export function buildPipelineEntities(
  language: UiLanguage,
  query: string,
  limit = COMMAND_PALETTE_RESULT_LIMIT,
): CommandPaletteEntity[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (normalizedQuery.length === 0) return [];

  const copy = AGENT_SETUP_COPY[language];
  const agentBehaviorHref = buildSettingsHref({
    section: 'agent_behavior',
    view: 'execution',
  });
  const matches: CommandPaletteEntity[] = [];

  for (const preset of AGENT_SETUP_PRESETS) {
    const presetId = preset.id as AgentSetupPresetId;
    const presetCopy = copy[presetId];
    const searchText = [
      preset.id,
      presetCopy.name,
      presetCopy.description,
      'pipeline',
      '管线',
      'orchestrator',
    ].join(' ').toLocaleLowerCase();
    if (!includesQuery(searchText, normalizedQuery)) continue;
    matches.push({
      id: `pipeline-${preset.id}`,
      href: agentBehaviorHref,
      label: presetCopy.name,
      description: presetCopy.description,
      meta: preset.id,
      searchText,
    });
  }
  return takeLimited(matches, limit);
}

export function buildSettingsEntities(
  language: UiLanguage,
  query: string,
  limit = COMMAND_PALETTE_RESULT_LIMIT,
): CommandPaletteEntity[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (normalizedQuery.length === 0) return [];

  const matches: CommandPaletteEntity[] = [];

  for (const section of SETTINGS_SECTIONS) {
    const sectionId = section.id as SettingsSectionId;
    const sectionName = section.label[language];
    const sectionSearch = [sectionId, sectionName, 'settings', '设置'].join(' ').toLocaleLowerCase();

    if (section.views.length === 0) {
      if (!includesQuery(sectionSearch, normalizedQuery)) continue;
      matches.push({
        id: `settings-${sectionId}`,
        href: buildSettingsHref({ section: sectionId }),
        label: sectionName,
        meta: sectionId,
        searchText: sectionSearch,
      });
      continue;
    }

    for (const view of section.views) {
      const viewName = view.label[language];
      const searchText = [
        sectionId,
        sectionName,
        view.id,
        viewName,
        SETTINGS_VIEW_SEARCH_ALIASES[`${sectionId}/${view.id}`] ?? '',
        'settings',
        '设置',
      ]
        .join(' ')
        .toLocaleLowerCase();
      if (!includesQuery(searchText, normalizedQuery)) continue;
      const isDefaultOnlyView = section.views.length === 1;
      matches.push({
        id: `settings-${sectionId}-${view.id}`,
        href: buildSettingsHref({
          section: sectionId,
          view: isDefaultOnlyView ? undefined : view.id,
        }),
        label: isDefaultOnlyView ? sectionName : `${sectionName} · ${viewName}`,
        description: isDefaultOnlyView ? undefined : viewName,
        meta: isDefaultOnlyView ? sectionId : `${sectionId}/${view.id}`,
        searchText,
      });
    }
  }

  return takeLimited(matches, limit);
}
