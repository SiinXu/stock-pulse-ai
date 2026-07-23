// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { SETTINGS_SECTION_IDS } from '../../../routing/routes';
import {
  SETTINGS_SECTIONS,
  getDefaultView,
  getSectionViews,
  getVisibleSections,
  hasHiddenAdvancedSections,
  isBeginnerEssentialSection,
  isSettingsSectionId,
  legacyToSectionView,
  normalizeSectionView,
  sectionLabel,
  sectionViewToLegacy,
  viewLabel,
} from '../settingsInformationArchitecture';

describe('settingsInformationArchitecture', () => {
  it('defines the 12 top-level sections in order', () => {
    expect(SETTINGS_SECTIONS.map((section) => section.id)).toEqual([
      'overview',
      'ai_models',
      'data_sources',
      'agent_behavior',
      'conversation',
      'reports',
      'alerts',
      'notifications',
      SETTINGS_SECTION_IDS.usage,
      'backtesting',
      'system_security',
      'advanced',
    ]);
  });

  it('gates advanced sections behind beginner-mode progressive disclosure', () => {
    // Full mode (and revealed advanced) always returns the complete list.
    expect(getVisibleSections(false, false, 'overview')).toBe(SETTINGS_SECTIONS);
    expect(getVisibleSections(true, true, 'overview')).toBe(SETTINGS_SECTIONS);
    expect(hasHiddenAdvancedSections(false, false)).toBe(false);

    // Beginner mode with advanced hidden shows only the essentials.
    const visible = getVisibleSections(true, false, 'overview').map((section) => section.id);
    expect(visible).toEqual(['overview', 'ai_models', 'data_sources', 'notifications']);
    expect(hasHiddenAdvancedSections(true, false)).toBe(true);
    expect(isBeginnerEssentialSection('ai_models')).toBe(true);
    expect(isBeginnerEssentialSection('backtesting')).toBe(false);

    // The currently-active advanced section is never hidden from the user.
    const withActiveAdvanced = getVisibleSections(true, false, 'backtesting').map((section) => section.id);
    expect(withActiveAdvanced).toContain('backtesting');
    expect(withActiveAdvanced).toContain('overview');
  });

  it('defines Usage & cost as a leaf section owned by TokenUsagePage', () => {
    expect(isSettingsSectionId(SETTINGS_SECTION_IDS.usage)).toBe(true);
    expect(sectionLabel(SETTINGS_SECTION_IDS.usage, 'en')).toBe('Usage & cost');
    expect(getSectionViews(SETTINGS_SECTION_IDS.usage)).toEqual([]);
    expect(getDefaultView(SETTINGS_SECTION_IDS.usage)).toBe('');
    expect(sectionViewToLegacy(SETTINGS_SECTION_IDS.usage, null))
      .toEqual({ category: 'base', sub: null });
    expect(normalizeSectionView(SETTINGS_SECTION_IDS.usage, 'unknown'))
      .toEqual({ section: SETTINGS_SECTION_IDS.usage, view: '' });
  });

  it('splits AI & Models into the four expected views with a default', () => {
    // No "advanced" view: the legacy Model Providers panel is retired and
    // Model Access (Connections) is the single entry for provider credentials.
    expect(getSectionViews('ai_models').map((view) => view.id)).toEqual([
      'overview',
      'connections',
      'task_routing',
      'reliability',
    ]);
    expect(getDefaultView('ai_models')).toBe('connections');
  });

  it('splits content-heavy sections into per-view tabs with a default', () => {
    expect(getSectionViews('alerts').map((view) => view.id)).toEqual(['routing', 'behavior', 'events']);
    expect(getDefaultView('alerts')).toBe('routing');
    expect(getSectionViews('data_sources').map((view) => view.id)).toEqual(['sources', 'intelligence', 'providers']);
    expect(getDefaultView('data_sources')).toBe('sources');
    expect(getSectionViews('system_security').map((view) => view.id)).toEqual(['runtime', 'general', 'service', 'security', 'about']);
    expect(getDefaultView('system_security')).toBe('runtime');
    expect(getSectionViews('advanced').map((view) => view.id)).toEqual(['raw_config', 'diagnostics', 'backup']);
    expect(getDefaultView('advanced')).toBe('raw_config');
  });

  it('exposes bilingual section and view labels', () => {
    expect(sectionLabel('ai_models', 'zh')).toBe('AI 与模型');
    expect(sectionLabel('ai_models', 'en')).toBe('AI & Models');
    expect(viewLabel('ai_models', 'connections', 'zh')).toBe('模型接入');
    expect(viewLabel('ai_models', 'connections', 'en')).toBe('Model Access');
    expect(viewLabel('ai_models', 'task_routing', 'zh')).toBe('任务路由');
    expect(viewLabel('ai_models', 'task_routing', 'en')).toBe('Task Routing');
  });

  it('recognizes valid section ids', () => {
    expect(isSettingsSectionId('ai_models')).toBe(true);
    expect(isSettingsSectionId('nope')).toBe(false);
  });

  it('maps legacy category/sub to the new section/view', () => {
    expect(legacyToSectionView('ai_model', 'model')).toEqual({ section: 'ai_models', view: 'connections' });
    // Retired providers sub (old deep links) also lands on Model Access.
    expect(legacyToSectionView('ai_model', 'providers')).toEqual({ section: 'ai_models', view: 'connections' });
    expect(legacyToSectionView('ai_model', null)).toEqual({ section: 'ai_models', view: 'connections' });
    expect(legacyToSectionView('notification', 'channels')).toEqual({ section: 'notifications', view: 'channels' });
    expect(legacyToSectionView('notification', 'rules')).toEqual({ section: 'alerts', view: 'routing' });
    expect(legacyToSectionView('data_source', 'source')).toEqual({ section: 'data_sources', view: 'sources' });
    expect(legacyToSectionView('data_source', 'providers')).toEqual({ section: 'data_sources', view: 'providers' });
    expect(legacyToSectionView('agent', null)).toEqual({ section: 'agent_behavior', view: 'execution' });
    expect(legacyToSectionView('backtest', null)).toEqual({ section: 'backtesting', view: 'engine' });
    expect(legacyToSectionView('system', null)).toEqual({ section: 'system_security', view: 'runtime' });
    expect(legacyToSectionView('base', null)).toEqual({ section: 'overview', view: 'readiness' });
    // Unknown categories fall back to the overview section.
    expect(legacyToSectionView('mystery', null)).toEqual({ section: 'overview', view: 'readiness' });
  });

  it('maps new section/view back to a renderable legacy category/sub', () => {
    expect(sectionViewToLegacy('ai_models', 'connections')).toEqual({ category: 'ai_model', sub: null });
    // Top-level Advanced renders its own aggregated card; the legacy mapping
    // must never resurrect a providers sub.
    for (const view of ['raw_config', 'diagnostics', 'backup']) {
      expect(sectionViewToLegacy('advanced', view)).toEqual({ category: 'ai_model', sub: null });
    }
    expect(sectionViewToLegacy('notifications', 'channels')).toEqual({ category: 'notification', sub: 'channels' });
    // All alerts views load the same backend bucket; the view only decides
    // which fields/cards render.
    for (const view of ['routing', 'behavior', 'events']) {
      expect(sectionViewToLegacy('alerts', view)).toEqual({ category: 'notification', sub: 'rules' });
    }
    for (const view of ['runtime', 'general', 'service', 'security', 'about']) {
      expect(sectionViewToLegacy('system_security', view)).toEqual({ category: 'system', sub: null });
    }
    expect(sectionViewToLegacy('data_sources', 'providers')).toEqual({ category: 'data_source', sub: 'providers' });
    expect(sectionViewToLegacy('data_sources', 'sources')).toEqual({ category: 'data_source', sub: 'source' });
    // The Intel Sources tab renders a dedicated panel but still loads the
    // `source` backend bucket so field data stays available.
    expect(sectionViewToLegacy('data_sources', 'intelligence')).toEqual({ category: 'data_source', sub: 'source' });
    expect(sectionViewToLegacy('system_security', 'runtime')).toEqual({ category: 'system', sub: null });
    expect(sectionViewToLegacy('backtesting', 'engine')).toEqual({ category: 'backtest', sub: null });
  });

  it('round-trips a legacy tab through the new IA back to a renderable tab', () => {
    for (const [category, sub] of [
      ['ai_model', 'model'],
      ['notification', 'channels'],
      ['data_source', 'providers'],
      ['system', null],
      ['backtest', null],
    ] as Array<[string, string | null]>) {
      const target = legacyToSectionView(category, sub);
      const legacy = sectionViewToLegacy(target.section, target.view);
      // The category is preserved so the correct panel renders.
      expect(legacy.category).toBe(category);
    }
  });

  it('normalizes unknown or partial section/view to a valid target', () => {
    expect(normalizeSectionView('ai_models', 'task_routing')).toEqual({ section: 'ai_models', view: 'task_routing' });
    // Unknown view -> section default.
    expect(normalizeSectionView('ai_models', 'bogus')).toEqual({ section: 'ai_models', view: 'connections' });
    // Retired alerts `rules` view (old deep links) falls back to the default tab.
    expect(normalizeSectionView('alerts', 'rules')).toEqual({ section: 'alerts', view: 'routing' });
    // Unknown section -> first section + its default view.
    expect(normalizeSectionView('bogus', null)).toEqual({ section: 'overview', view: 'readiness' });
    // Nulls -> first section default.
    expect(normalizeSectionView(null, null)).toEqual({ section: 'overview', view: 'readiness' });
  });
});
