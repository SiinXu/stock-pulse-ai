import type { UiLanguage } from '../i18n/uiText';
import { BUILTIN_STRATEGY_TEXT } from '../locales/strategies';

export type StrategyDisplaySource = {
  id: string;
  name?: string;
  title?: string;
  description?: string;
  category?: string;
  tag?: string;
  tags?: string[];
  nameZh?: string;
  nameEn?: string;
  descriptionZh?: string;
  descriptionEn?: string;
  categoryZh?: string;
  categoryEn?: string;
  name_zh?: string;
  name_en?: string;
  description_zh?: string;
  description_en?: string;
  category_zh?: string;
  category_en?: string;
};

export type StrategyDisplay = {
  name: string;
  description: string;
  category: string;
};

const firstText = (...values: Array<string | undefined>): string =>
  values.find((value) => typeof value === 'string' && value.trim())?.trim() ?? '';

export function getStrategyDisplay(
  strategy: StrategyDisplaySource,
  language: UiLanguage,
): StrategyDisplay {
  const localized = BUILTIN_STRATEGY_TEXT[language][strategy.id];
  const localizedName = language === 'en'
    ? firstText(strategy.nameEn, strategy.name_en)
    : firstText(strategy.nameZh, strategy.name_zh);
  const localizedDescription = language === 'en'
    ? firstText(strategy.descriptionEn, strategy.description_en)
    : firstText(strategy.descriptionZh, strategy.description_zh);
  const localizedCategory = language === 'en'
    ? firstText(strategy.categoryEn, strategy.category_en)
    : firstText(strategy.categoryZh, strategy.category_zh);

  return {
    name: firstText(
      localizedName,
      language === 'zh' ? strategy.name : undefined,
      localized?.name,
      strategy.name,
      strategy.title,
      strategy.id,
    ),
    description: firstText(
      localizedDescription,
      language === 'zh' ? strategy.description : undefined,
      localized?.description,
      strategy.description,
      strategy.id,
    ),
    category: firstText(
      localizedCategory,
      language === 'zh' ? strategy.category : undefined,
      localized?.category,
      strategy.category,
      strategy.tag,
      strategy.tags?.[0],
      strategy.id,
    ),
  };
}
