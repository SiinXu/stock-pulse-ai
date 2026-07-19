// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { InlineAlert, Pressable } from '../common';
import type { UiLang } from './settingsInformationArchitecture';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';

export interface ErrorSummaryEntry {
  /** Config key with the validation error. */
  key: string;
  /** Human-friendly field label. */
  label: string;
  /** Validation message to show under the field label. */
  message: string;
  /** Section/view that owns the field (from the placement map). */
  section: string;
  view: string;
}

interface SettingsErrorSummaryProps {
  entries: ErrorSummaryEntry[];
  onJump: (entry: ErrorSummaryEntry) => void;
  language: UiLang;
}

/**
 * Page-level validation summary. Lists every errored field across all sections
 * and lets the user jump straight to the owning section/view and focus the
 * field, so errors on a section that isn't currently open are still reachable.
 */
export const SettingsErrorSummary: React.FC<SettingsErrorSummaryProps> = ({
  entries,
  onJump,
  language,
}) => {
  if (entries.length === 0) {
    return null;
  }
  const text = SETTINGS_MISC_TEXT[language];
  const title = formatUiText(
    entries.length === 1 ? text.errorSummaryOne : text.errorSummary,
    { count: entries.length },
  );
  const jumpHint = text.jumpToField;
  return (
    <InlineAlert
      variant="danger"
      title={title}
      className="rounded-2xl"
      message={(
        <ul className="mt-1 space-y-1.5">
          {entries.map((entry) => (
            <li key={entry.key}>
              <Pressable
                type="button"
                onClick={() => onJump(entry)}
                aria-label={`${jumpHint}: ${entry.label}`}
                className="flex w-full flex-col rounded-lg px-2 py-1 text-left transition-colors hover:bg-[hsl(var(--color-danger-alert-text)/0.08)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <span className="text-sm font-medium underline-offset-2 group-hover:underline">{entry.label}</span>
                <span className="text-xs opacity-80">{entry.message}</span>
              </Pressable>
            </li>
          ))}
        </ul>
      )}
    />
  );
};
