import { describe, expect, it } from 'vitest';
import {
  SETTINGS_SECTIONS,
  getDefaultView,
  getSectionViews,
  isSettingsSectionId,
  legacyToSectionView,
  normalizeSectionView,
  sectionLabel,
  sectionViewToLegacy,
  viewLabel,
} from '../settingsInformationArchitecture';

describe('settingsInformationArchitecture', () => {
  it('defines the 11 top-level sections in order', () => {
    expect(SETTINGS_SECTIONS.map((section) => section.id)).toEqual([
      'overview',
      'ai_models',
      'data_sources',
      'agent_behavior',
      'conversation',
      'reports',
      'alerts',
      'notifications',
      'backtesting',
      'system_security',
      'advanced',
    ]);
  });

  it('splits AI & Models into the five expected views with a default', () => {
    expect(getSectionViews('ai_models').map((view) => view.id)).toEqual([
      'overview',
      'connections',
      'task_routing',
      'reliability',
      'advanced',
    ]);
    expect(getDefaultView('ai_models')).toBe('connections');
  });

  it('exposes bilingual section and view labels', () => {
    expect(sectionLabel('ai_models', 'zh')).toBe('AI 与模型');
    expect(sectionLabel('ai_models', 'en')).toBe('AI & Models');
    expect(viewLabel('ai_models', 'task_routing', 'zh')).toBe('任务路由');
    expect(viewLabel('ai_models', 'task_routing', 'en')).toBe('Task Routing');
  });

  it('recognizes valid section ids', () => {
    expect(isSettingsSectionId('ai_models')).toBe(true);
    expect(isSettingsSectionId('nope')).toBe(false);
  });

  it('maps legacy category/sub to the new section/view', () => {
    expect(legacyToSectionView('ai_model', 'model')).toEqual({ section: 'ai_models', view: 'connections' });
    expect(legacyToSectionView('ai_model', 'providers')).toEqual({ section: 'ai_models', view: 'advanced' });
    expect(legacyToSectionView('notification', 'channels')).toEqual({ section: 'notifications', view: 'channels' });
    expect(legacyToSectionView('notification', 'rules')).toEqual({ section: 'alerts', view: 'rules' });
    expect(legacyToSectionView('data_source', 'source')).toEqual({ section: 'data_sources', view: 'providers' });
    expect(legacyToSectionView('agent', null)).toEqual({ section: 'agent_behavior', view: 'execution' });
    expect(legacyToSectionView('backtest', null)).toEqual({ section: 'backtesting', view: 'engine' });
    expect(legacyToSectionView('system', null)).toEqual({ section: 'system_security', view: 'runtime' });
    expect(legacyToSectionView('base', null)).toEqual({ section: 'overview', view: 'readiness' });
    // Unknown categories fall back to the overview section.
    expect(legacyToSectionView('mystery', null)).toEqual({ section: 'overview', view: 'readiness' });
  });

  it('maps new section/view back to a renderable legacy category/sub', () => {
    expect(sectionViewToLegacy('ai_models', 'connections')).toEqual({ category: 'ai_model', sub: 'model' });
    expect(sectionViewToLegacy('ai_models', 'advanced')).toEqual({ category: 'ai_model', sub: 'providers' });
    expect(sectionViewToLegacy('notifications', 'channels')).toEqual({ category: 'notification', sub: 'channels' });
    expect(sectionViewToLegacy('alerts', 'rules')).toEqual({ category: 'notification', sub: 'rules' });
    expect(sectionViewToLegacy('data_sources', 'providers')).toEqual({ category: 'data_source', sub: 'providers' });
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
    // Unknown section -> first section + its default view.
    expect(normalizeSectionView('bogus', null)).toEqual({ section: 'overview', view: 'readiness' });
    // Nulls -> first section default.
    expect(normalizeSectionView(null, null)).toEqual({ section: 'overview', view: 'readiness' });
  });
});
