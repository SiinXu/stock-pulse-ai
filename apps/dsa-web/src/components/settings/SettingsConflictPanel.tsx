// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SETTINGS_PAGE_TEXT } from '../../locales/settingsPage';
import { resolveSettingsFieldTitle } from '../../locales/settingsFieldTitle';
import { Button } from '../common';

export type SettingsConflictField = {
  key: string;
  title?: string;
  server?: string;
  local?: string;
  isSensitive?: boolean;
};

export type SettingsConflictPanelProps = {
  fields: SettingsConflictField[];
  onResolveField: (key: string, choice: 'server' | 'local') => void;
  onResolveAll: (choice: 'server' | 'local') => void;
};

/** Version-conflict resolution UI shown above the settings form. */
const SettingsConflictPanel: React.FC<SettingsConflictPanelProps> = ({
  fields,
  onResolveField,
  onResolveAll,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];

  return (
    <section
      className="mt-3 space-y-3 rounded-xl border border-warning/40 bg-warning/5 p-4"
      aria-labelledby="settings-conflict-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 id="settings-conflict-title" className="text-sm font-semibold text-foreground">
            {settingsText.conflictTitle}
          </h2>
          <p className="text-xs leading-5 text-secondary-text">
            {settingsText.conflictDescription}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="compact" onClick={() => onResolveAll('server')}>
            {settingsText.useAllServer}
          </Button>
          <Button type="button" variant="secondary" size="compact" onClick={() => onResolveAll('local')}>
            {settingsText.keepAllLocal}
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        {fields.map((field) => (
          <div key={field.key} className="rounded-lg border border-[var(--settings-border)] bg-background/70 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {resolveSettingsFieldTitle({
                    itemKey: field.key,
                    fallbackTitle: field.title || field.key,
                    language: uiLanguage,
                  })}
                </p>
                <p className="text-xs text-muted-text">{field.key}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="secondary" size="compact" onClick={() => onResolveField(field.key, 'server')}>
                  {settingsText.useServer}
                </Button>
                <Button type="button" variant="primary" size="compact" onClick={() => onResolveField(field.key, 'local')}>
                  {settingsText.keepLocal}
                </Button>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded-md bg-[var(--settings-surface)] px-3 py-2">
                <p className="text-xs font-medium text-muted-text">{settingsText.serverValue}</p>
                <p className="mt-1 break-all text-xs text-secondary-text">
                  {field.isSensitive ? settingsText.hiddenServerValue : field.server || settingsText.emptyValue}
                </p>
              </div>
              <div className="rounded-md bg-[var(--settings-surface)] px-3 py-2">
                <p className="text-xs font-medium text-muted-text">{settingsText.localValue}</p>
                <p className="mt-1 break-all text-xs text-secondary-text">
                  {field.isSensitive ? settingsText.hiddenLocalValue : field.local || settingsText.emptyValue}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SettingsConflictPanel;
