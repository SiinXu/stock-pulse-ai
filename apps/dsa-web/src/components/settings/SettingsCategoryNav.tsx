import type React from 'react';
import { Bell, Bot, Database, Layers3, LineChart, Settings2, SlidersHorizontal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Badge } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getCategoryTitle } from '../../utils/systemConfigI18n';
import type { SystemConfigCategory, SystemConfigCategorySchema, SystemConfigItem } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';

interface SettingsCategoryNavProps {
  categories: SystemConfigCategorySchema[];
  itemsByCategory: Record<string, SystemConfigItem[]>;
  activeCategory: string;
  onSelect: (category: string) => void;
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

export const SettingsCategoryNav: React.FC<SettingsCategoryNavProps> = ({
  categories,
  itemsByCategory,
  activeCategory,
  onSelect,
}) => {
  const { language, t } = useUiLanguage();

  return (
    <nav
      className="h-full"
      aria-label={t('settings.categoryNavTitle')}
    >
      <div className="flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1.5 lg:overflow-visible lg:pb-0">
        {CATEGORY_GROUP_ORDER.flatMap((group) => {
          const groupCategories = categories.filter(
            (category) => (CATEGORY_TO_GROUP.get(category.category) ?? 'other') === group.id,
          );
          if (!groupCategories.length) {
            return [];
          }

          return [
            <p
              key={`group-${group.id}`}
              className="hidden px-3 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-muted-text first:pt-0 lg:block"
            >
              {t(group.titleKey)}
            </p>,
            ...groupCategories.map((category) => {
              const isActive = category.category === activeCategory;
              const count = (itemsByCategory[category.category] || []).length;
              const title = getCategoryTitle(category.category, category.title, language);
              const Icon = categoryIconMap[category.category] ?? Layers3;

              return (
                <button
                  key={category.category}
                  type="button"
                  className={cn(
                    'flex min-w-[9rem] items-center gap-2 rounded-md border px-3 py-2.5 text-left transition-[background-color,border-color,box-shadow] duration-200 lg:min-w-0 lg:w-full lg:items-center lg:gap-3 lg:px-3 lg:py-3',
                    isActive
                      ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-foreground'
                      : 'border-transparent bg-transparent hover:border-[var(--settings-border)] hover:bg-[var(--settings-surface-hover)]',
                  )}
                  onClick={() => onSelect(category.category)}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon
                    className={cn('h-4 w-4 shrink-0', isActive ? 'text-foreground' : 'text-muted-text')}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block truncate text-sm font-medium', isActive ? 'text-foreground' : 'text-secondary-text')}>
                      {title}
                    </span>
                  </span>
                  <Badge
                    variant="default"
                    size="sm"
                    className={cn(
                      'shrink-0 px-1.5 py-0 text-[11px]',
                      isActive
                        ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-foreground'
                        : 'border-[var(--settings-border)] bg-[var(--settings-surface)] text-muted-text',
                    )}
                  >
                    {count}
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
