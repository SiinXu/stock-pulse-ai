// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { Palette } from 'lucide-react';
import { listThemePacks } from '../../design/themePacks';
import type { ThemePackId } from '../../design/theme';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Select } from '../common/Select';
import { useThemeAppearance } from './ThemeAppearanceProvider';

type ThemePackSelectProps = {
  wrapperClassName?: string;
  triggerClassName?: string;
  iconClassName?: string;
};

/** Pack labels are proper nouns (Classic / Slate) — no new i18n keys. */
export const ThemePackSelect: React.FC<ThemePackSelectProps> = ({
  wrapperClassName,
  triggerClassName,
  iconClassName,
}) => {
  const { pack, setPack } = useThemeAppearance();
  const { t } = useUiLanguage();
  const packs = listThemePacks();

  return (
    <div
      className={cn(
        triggerClassName
          ?? 'flex h-11 min-h-11 w-full items-center gap-2 rounded-lg px-3 text-sm text-secondary-text',
        wrapperClassName,
      )}
      data-testid="theme-pack-select"
    >
      <Palette className={iconClassName ?? 'h-4 w-4 shrink-0'} aria-hidden="true" />
      <Select
        value={pack}
        onChange={(next) => setPack(next as ThemePackId)}
        options={packs.map((entry) => ({
          value: entry.id,
          label: entry.displayName,
        }))}
        ariaLabel={t('theme.theme')}
        className="min-w-0 flex-1 [&>div]:w-full"
        triggerClassName="h-11 min-h-11 border-0 bg-transparent px-0 text-sm font-normal hover:bg-transparent sm:h-11 sm:min-h-11"
        menuAlign="start"
        menuPlacement="right"
      />
    </div>
  );
};
