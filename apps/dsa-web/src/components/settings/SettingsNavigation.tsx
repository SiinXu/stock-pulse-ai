// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { SegmentedControl, Select } from '../common';
import { cn } from '../../utils/cn';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';
import {
  getSectionViews,
  getVisibleSections,
  hasHiddenAdvancedSections,
  sectionLabel,
  viewLabel,
  type SettingsSectionId,
  type UiLang,
} from './settingsInformationArchitecture';

export interface SectionStatus {
  /** A validation error is present somewhere in this section. */
  hasError?: boolean;
  /** Unsaved draft edits exist in this section. */
  isDirty?: boolean;
  /** The section needs user action (e.g. incomplete required setup). */
  needsAction?: boolean;
}

type SectionStatusMap = Partial<Record<SettingsSectionId, SectionStatus>>;

function statusDotClass(status: SectionStatus | undefined): string | null {
  if (!status) {
    return null;
  }
  // Priority: error > needs-action > dirty. Badges convey state only — never counts.
  if (status.hasError) {
    return 'bg-danger';
  }
  if (status.needsAction) {
    return 'bg-info';
  }
  if (status.isDirty) {
    return 'bg-warning';
  }
  return null;
}

function statusLabel(status: SectionStatus | undefined, language: UiLang): string | null {
  const text = SETTINGS_MISC_TEXT[language];
  const dot = statusDotClass(status);
  if (!dot || !status) {
    return null;
  }
  if (status.hasError) {
    return text.statusError;
  }
  if (status.needsAction) {
    return text.statusAction;
  }
  return text.statusDirty;
}

interface SettingsSectionNavProps {
  activeSection: SettingsSectionId;
  onSelectSection: (section: SettingsSectionId) => void;
  /**
   * Mobile-only variant of onSelectSection. When the compact selector is used
   * (small screens) the caller usually wants to move focus to the content
   * region so the newly selected section is announced and scrolled into view.
   * Falls back to onSelectSection when omitted.
   */
  onMobileSelectSection?: (section: SettingsSectionId) => void;
  sectionStatus?: SectionStatusMap;
  language: UiLang;
  navLabel: string;
  /** Beginner mode hides advanced sections behind an explicit reveal. */
  beginnerMode?: boolean;
  /** Whether the user has revealed the advanced sections this session. */
  advancedRevealed?: boolean;
  /** Reveal the hidden advanced sections (beginner mode only). */
  onRevealAdvanced?: () => void;
}

/**
 * First-level settings navigation. On desktop it's a vertical sidebar; on
 * mobile (390px) it collapses to a compact single-select so the current section
 * stays visible and the content is reachable in one tap — the whole category
 * tree is never unfurled above the fold.
 */
export const SettingsSectionNav: React.FC<SettingsSectionNavProps> = ({
  activeSection,
  onSelectSection,
  onMobileSelectSection,
  sectionStatus,
  language,
  navLabel,
  beginnerMode = false,
  advancedRevealed = false,
  onRevealAdvanced,
}) => {
  const visibleSections = getVisibleSections(beginnerMode, advancedRevealed, activeSection);
  const showRevealAdvanced = hasHiddenAdvancedSections(beginnerMode, advancedRevealed)
    && onRevealAdvanced !== undefined;
  const revealLabel = SETTINGS_MISC_TEXT[language].showAdvanced;
  return (
  <nav aria-label={navLabel}>
    {/* Mobile: compact selector (short path, current section always visible). */}
    <div className="md:hidden space-y-2">
      <Select
        id="settings-section-select"
        ariaLabel={navLabel}
        className="w-full [&>div]:w-full"
        triggerClassName="min-h-11 rounded-md border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-2.5 text-sm"
        value={activeSection}
        onChange={(value) => (onMobileSelectSection ?? onSelectSection)(value as SettingsSectionId)}
        options={visibleSections.map((section) => {
          const label = statusLabel(sectionStatus?.[section.id], language);
          return {
            value: section.id,
            label: `${sectionLabel(section.id, language)}${label ? ` · ${label}` : ''}`,
          };
        })}
      />
      {showRevealAdvanced ? (
        <button
          type="button"
          className="min-h-11 w-full rounded-md border border-dashed border-[var(--settings-border)] px-3 py-2 text-left text-sm text-secondary-text hover:bg-[var(--settings-surface-hover)]"
          onClick={onRevealAdvanced}
        >
          {revealLabel}
        </button>
      ) : null}
    </div>

    {/* Desktop: vertical sidebar with per-section status dots. */}
    <ul className="hidden gap-1.5 md:flex md:flex-col">
      {visibleSections.map((section) => {
        const isActive = section.id === activeSection;
        const status = sectionStatus?.[section.id];
        const dot = statusDotClass(status);
        const dotLabel = statusLabel(status, language);
        return (
          <li key={section.id}>
            <button
              type="button"
              className={cn(
                'flex min-h-11 w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm transition-[background-color,border-color] duration-200',
                isActive
                  ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-foreground'
                  : 'border-transparent bg-transparent text-secondary-text hover:border-[var(--settings-border)] hover:bg-[var(--settings-surface-hover)]',
              )}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => onSelectSection(section.id)}
            >
              <span className="min-w-0 flex-1 truncate">{sectionLabel(section.id, language)}</span>
              {dot ? (
                <span className={cn('h-2 w-2 shrink-0 rounded-full', dot)} role="img" aria-label={dotLabel ?? undefined} />
              ) : null}
            </button>
          </li>
        );
      })}
      {showRevealAdvanced ? (
        <li>
          <button
            type="button"
            className="flex min-h-11 w-full items-center rounded-lg border border-dashed border-[var(--settings-border)] px-3 py-2.5 text-left text-sm text-secondary-text transition-[background-color,border-color] duration-200 hover:bg-[var(--settings-surface-hover)]"
            onClick={onRevealAdvanced}
          >
            <span className="min-w-0 flex-1 truncate">{revealLabel}</span>
          </button>
        </li>
      ) : null}
    </ul>
  </nav>
  );
};

interface SettingsViewTabsProps {
  section: SettingsSectionId;
  activeView: string;
  onSelectView: (view: string) => void;
  language: UiLang;
  tabsLabel: string;
}

/**
 * Second-level navigation shown in the content area. Only renders when the
 * active section has more than one view (currently AI & Models); otherwise the
 * section has a single implicit view and no tabs are shown.
 */
export const SettingsViewTabs: React.FC<SettingsViewTabsProps> = ({
  section,
  activeView,
  onSelectView,
  language,
  tabsLabel,
}) => {
  const views = getSectionViews(section);
  if (views.length <= 1) {
    return null;
  }
  return (
    <SegmentedControl
      value={activeView}
      options={views.map((view) => ({
        value: view.id,
        label: viewLabel(section, view.id, language),
      }))}
      onChange={onSelectView}
      ariaLabel={tabsLabel}
    />
  );
};
