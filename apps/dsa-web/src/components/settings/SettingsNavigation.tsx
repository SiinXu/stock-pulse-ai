import type React from 'react';
import { cn } from '../../utils/cn';
import {
  SETTINGS_SECTIONS,
  getSectionViews,
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
  const dot = statusDotClass(status);
  if (!dot || !status) {
    return null;
  }
  if (status.hasError) {
    return language === 'en' ? 'has errors' : '有错误';
  }
  if (status.needsAction) {
    return language === 'en' ? 'needs action' : '需要操作';
  }
  return language === 'en' ? 'unsaved changes' : '有未保存修改';
}

interface SettingsSectionNavProps {
  activeSection: SettingsSectionId;
  onSelectSection: (section: SettingsSectionId) => void;
  sectionStatus?: SectionStatusMap;
  language: UiLang;
  navLabel: string;
}

/**
 * First-level settings navigation. Renders a vertical sidebar on desktop and a
 * horizontally scrollable pill row on mobile (390px) so the content stays above
 * the fold instead of unfurling the whole category tree.
 */
export const SettingsSectionNav: React.FC<SettingsSectionNavProps> = ({
  activeSection,
  onSelectSection,
  sectionStatus,
  language,
  navLabel,
}) => (
  <nav aria-label={navLabel}>
    <ul className="flex gap-1.5 overflow-x-auto pb-1 md:flex-col md:overflow-visible md:pb-0">
      {SETTINGS_SECTIONS.map((section) => {
        const isActive = section.id === activeSection;
        const status = sectionStatus?.[section.id];
        const dot = statusDotClass(status);
        const dotLabel = statusLabel(status, language);
        return (
          <li key={section.id} className="shrink-0 md:shrink">
            <button
              type="button"
              className={cn(
                'flex w-full items-center gap-2 whitespace-nowrap rounded-md border px-3 py-2.5 text-left text-sm transition-[background-color,border-color] duration-200 md:whitespace-normal',
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
    </ul>
  </nav>
);

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
    <div
      role="tablist"
      aria-label={tabsLabel}
      className="flex gap-1 overflow-x-auto border-b border-[var(--settings-border)] pb-px"
    >
      {views.map((view) => {
        const isActive = view.id === activeView;
        return (
          <button
            key={view.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={cn(
              'whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors duration-200',
              isActive
                ? 'border-foreground font-medium text-foreground'
                : 'border-transparent text-secondary-text hover:text-foreground',
            )}
            onClick={() => onSelectView(view.id)}
          >
            {viewLabel(section, view.id, language)}
          </button>
        );
      })}
    </div>
  );
};
