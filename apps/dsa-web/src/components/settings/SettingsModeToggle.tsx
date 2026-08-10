// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { SegmentedControl, Surface } from '../common';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';
import type { UiLanguage } from '../../i18n/uiLanguages';

export type SettingsDisplayMode = 'essentials' | 'expert';

export type SettingsModeToggleProps = {
  mode: SettingsDisplayMode;
  onModeChange: (mode: SettingsDisplayMode) => void;
  language: UiLanguage;
};

/**
 * Essentials vs Expert progressive-disclosure control for Settings.
 * Presentation-only: deep links and advanced sections remain reachable.
 */
export const SettingsModeToggle: React.FC<SettingsModeToggleProps> = ({
  mode,
  onModeChange,
  language,
}) => {
  const text = SETTINGS_MISC_TEXT[language];
  return (
    <Surface
      level="interactive"
      className="space-y-2 px-3 py-2.5"
      data-testid="settings-mode-toggle"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{text.settingsModeLabel}</p>
        <p className="mt-0.5 text-xs text-muted-text">{text.settingsModeHint}</p>
      </div>
      <SegmentedControl
        id="settings-display-mode"
        semantics="single-select"
        ariaLabel={text.settingsModeLabel}
        value={mode}
        onChange={onModeChange}
        options={[
          { value: 'essentials', label: text.essentialsModeLabel },
          { value: 'expert', label: text.expertModeLabel },
        ]}
      />
    </Surface>
  );
};

export default SettingsModeToggle;
