import type React from 'react';
import { InlineAlert } from '../common';
import type { UiLang } from './settingsInformationArchitecture';

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
  const title = language === 'en'
    ? `${entries.length} setting${entries.length > 1 ? 's' : ''} ${entries.length > 1 ? 'need' : 'needs'} attention`
    : `有 ${entries.length} 项配置需要修正`;
  const jumpHint = language === 'en' ? 'Go to field' : '前往修正';
  return (
    <InlineAlert
      variant="danger"
      title={title}
      className="rounded-2xl"
      message={(
        <ul className="mt-1 space-y-1.5">
          {entries.map((entry) => (
            <li key={entry.key}>
              <button
                type="button"
                onClick={() => onJump(entry)}
                aria-label={`${jumpHint}: ${entry.label}`}
                className="flex w-full flex-col rounded-md px-2 py-1 text-left transition-colors hover:bg-[hsl(var(--color-danger-alert-text)/0.08)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <span className="text-sm font-medium underline-offset-2 group-hover:underline">{entry.label}</span>
                <span className="text-xs opacity-80">{entry.message}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    />
  );
};
