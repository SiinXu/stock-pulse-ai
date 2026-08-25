// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { CheckCircle2, CircleAlert, Clock, RefreshCw } from 'lucide-react';
import { Button } from '../../common';
import { getCategoryTitle } from '../../../utils/systemConfigI18n';
import type { SystemConfigCategory } from '../../../types/systemConfig';
import type { UiLanguage } from '../../../i18n/uiText';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';
import {
  type SettingsGroupSaveState,
  type SettingsSaveStatus,
} from '../autosaveMachine';

type SettingsSaveActionsProps = {
  groupSaveStates: Record<string, SettingsGroupSaveState>;
  activeSaveGroup: string;
  activeGroupDirtyCount: number;
  isLoading: boolean;
  uiLanguage: UiLanguage;
  onRetryGroup: (group: string) => void;
  onRestoreGroup: (group: string) => void;
  onRequestResetGroup: () => void;
};

const saveStatusLabel = (status: SettingsSaveStatus, settingsText: (typeof SETTINGS_PAGE_TEXT)[UiLanguage]): string => {
  switch (status) {
    case 'dirty': return settingsText.autosaveScheduled;
    case 'scheduled': return settingsText.autosaveScheduled;
    case 'saving': return settingsText.autosaveSaving;
    case 'saved': return settingsText.autosaveSaved;
    case 'failed': return settingsText.autosaveFailed;
    case 'conflicted': return settingsText.autosaveConflicted;
    default: return '';
  }
};

const SettingsSaveActions: React.FC<SettingsSaveActionsProps> = ({
  groupSaveStates,
  activeSaveGroup,
  activeGroupDirtyCount,
  isLoading,
  uiLanguage,
  onRetryGroup,
  onRestoreGroup,
  onRequestResetGroup,
}) => {
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];
  const visibleGroupSaveStates = Object.entries(groupSaveStates)
    .filter(([, state]) => state.status !== 'idle');
  if (visibleGroupSaveStates.length === 0 && activeGroupDirtyCount === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2" aria-live="polite">
      {visibleGroupSaveStates.map(([group, state]) => (
        <span
          key={group}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-[var(--settings-border)] px-2.5 text-xs text-secondary-text"
        >
          {state.status === 'saved' ? (
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
          ) : state.status === 'failed' || state.status === 'conflicted' ? (
            <CircleAlert className="h-4 w-4 text-danger" aria-hidden="true" />
          ) : (
            <Clock className="h-4 w-4 text-warning" aria-hidden="true" />
          )}
          <span>{getCategoryTitle(group as SystemConfigCategory, group, uiLanguage)}: {saveStatusLabel(state.status, settingsText)}</span>
          {state.status === 'failed' ? (
            <button type="button" className="settings-accent-text inline-flex min-h-11 min-w-11 items-center justify-center px-1 underline" onClick={() => onRetryGroup(group)}>
              {settingsText.autosaveRetry}
            </button>
          ) : null}
          {state.status === 'failed' || state.status === 'conflicted' ? (
            <button type="button" className="inline-flex min-h-11 min-w-11 items-center justify-center px-1 text-danger underline" onClick={() => onRestoreGroup(group)}>
              {settingsText.autosaveRestore}
            </button>
          ) : null}
        </span>
      ))}
      {activeGroupDirtyCount > 0 ? (
        <Button
          type="button"
          variant="secondary"
          size="default"
          onClick={onRequestResetGroup}
          disabled={isLoading || groupSaveStates[activeSaveGroup]?.status === 'saving'}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {settingsText.autosaveResetGroup}
        </Button>
      ) : null}
    </div>
  );
};

export default SettingsSaveActions;
