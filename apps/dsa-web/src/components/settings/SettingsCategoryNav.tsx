import type React from 'react';
import { Bell, Bot, Database, Layers3, LineChart, MessagesSquare, Plug, Settings2, SlidersHorizontal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Badge } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getCategoryTitle } from '../../utils/systemConfigI18n';
import type { SystemConfigCategory, SystemConfigCategorySchema, SystemConfigItem } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { getSubCategoryCount, getSubCategoryOfKey, getVisibleSubCategories } from './settingsSubCategories';

interface SettingsCategoryNavProps {
  categories: SystemConfigCategorySchema[];
  itemsByCategory: Record<string, SystemConfigItem[]>;
  activeCategory: string;
  activeSubCategory: string | null;
  dirtyKeys?: string[];
  onSelectTab: (category: string, subCategory: string | null) => void;
}

const categoryIconMap: Partial<Record<SystemConfigCategory, LucideIcon>> = {
  system: Settings2,
  base: SlidersHorizontal,
  data_source: Database,
  ai_model: Layers3,
  notification: Bell,
  agent: Bot,
  backtest: LineChart,
};

// Distinct icons for categories split into multiple flat tabs, keyed by
// `${category}:${subId}`.
const subIconMap: Record<string, LucideIcon> = {
  'ai_model:providers': Layers3,
  'data_source:providers': Plug,
  'notification:channels': MessagesSquare,
};

const CATEGORY_GROUP_ORDER: Array<{ id: string; titleKey: UiTextKey; categories: SystemConfigCategory[] }> = [
  { id: 'intelligence', titleKey: 'settings.categoryGroupIntelligence', categories: ['ai_model', 'agent'] },
  { id: 'data', titleKey: 'settings.categoryGroupData', categories: ['data_source', 'backtest'] },
  { id: 'notification', titleKey: 'settings.categoryGroupNotification', categories: ['notification'] },
  { id: 'system', titleKey: 'settings.categoryGroupSystem', categories: ['base', 'system'] },
  { id: 'other', titleKey: 'settings.categoryGroupOther', categories: [] },
];

const CATEGORY_TO_GROUP = new Map<string, string>();
for (const group of CATEGORY_GROUP_ORDER) {
  for (const category of group.categories) {
    CATEGORY_TO_GROUP.set(category, group.id);
  }
}

interface FlatTab {
  key: string;
  category: string;
  subCategory: string | null;
  title: string;
  count: number;
  icon: LucideIcon;
  isActive: boolean;
  isDirty: boolean;
}

export const SettingsCategoryNav: React.FC<SettingsCategoryNavProps> = ({
  categories,
  itemsByCategory,
  activeCategory,
  activeSubCategory,
  dirtyKeys,
  onSelectTab,
}) => {
  const { language, t } = useUiLanguage();
  const dirtySet = new Set(dirtyKeys ?? []);
  const isTabDirty = (category: string, subCategory: string | null): boolean => {
    if (dirtySet.size === 0) {
      return false;
    }
    return (itemsByCategory[category] || []).some(
      (item) =>
        dirtySet.has(item.key) &&
        (subCategory === null || getSubCategoryOfKey(category, item.key) === subCategory),
    );
  };

  return (
    <nav className="h-full" aria-label={t('settings.categoryNavTitle')}>
      <div className="space-y-1.5">
        {CATEGORY_GROUP_ORDER.flatMap((group) => {
          const groupCategories = categories.filter(
            (category) => (CATEGORY_TO_GROUP.get(category.category) ?? 'other') === group.id,
          );
          if (!groupCategories.length) {
            return [];
          }

          const tabs: FlatTab[] = [];
          for (const category of groupCategories) {
            const subCategories = getVisibleSubCategories(category.category, itemsByCategory);
            if (subCategories.length === 0) {
              tabs.push({
                key: category.category,
                category: category.category,
                subCategory: null,
                title: getCategoryTitle(category.category, category.title, language),
                count: (itemsByCategory[category.category] || []).length,
                icon: categoryIconMap[category.category] ?? Layers3,
                isActive: category.category === activeCategory && activeSubCategory === null,
                isDirty: isTabDirty(category.category, null),
              });
              continue;
            }
            for (const sub of subCategories) {
              tabs.push({
                key: `${category.category}:${sub.id}`,
                category: category.category,
                subCategory: sub.id,
                title: t(sub.titleKey),
                count: getSubCategoryCount(category.category, sub.id, itemsByCategory),
                icon: subIconMap[`${category.category}:${sub.id}`] ?? categoryIconMap[category.category] ?? Layers3,
                isActive: category.category === activeCategory && sub.id === activeSubCategory,
                isDirty: isTabDirty(category.category, sub.id),
              });
            }
          }

          return [
            <p
              key={`group-${group.id}`}
              className="px-3 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-muted-text first:pt-0"
            >
              {t(group.titleKey)}
            </p>,
            ...tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.key}
                  type="button"
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md border px-3 py-3 text-left transition-[background-color,border-color,box-shadow] duration-200',
                    tab.isActive
                      ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-foreground'
                      : 'border-transparent bg-transparent hover:border-[var(--settings-border)] hover:bg-[var(--settings-surface-hover)]',
                  )}
                  onClick={() => onSelectTab(tab.category, tab.subCategory)}
                  aria-current={tab.isActive ? 'page' : undefined}
                >
                  <Icon
                    className={cn('h-4 w-4 shrink-0', tab.isActive ? 'text-foreground' : 'text-muted-text')}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block truncate text-sm font-medium', tab.isActive ? 'text-foreground' : 'text-secondary-text')}>
                      {tab.title}
                    </span>
                  </span>
                  {tab.isDirty ? (
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--primary)]"
                      role="img"
                      aria-label={t('settings.unsavedBadge')}
                    />
                  ) : null}
                  <Badge
                    variant="default"
                    size="sm"
                    className={cn(
                      'shrink-0 px-1.5 py-0 text-[11px]',
                      tab.isActive
                        ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-foreground'
                        : 'border-[var(--settings-border)] bg-[var(--settings-surface)] text-muted-text',
                    )}
                  >
                    {tab.count}
                  </Badge>
                </button>
              );
            }),
          ];
        })}
      </div>
    </nav>
  );
};
