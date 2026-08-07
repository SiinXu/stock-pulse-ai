// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, RefreshCw, Upload } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { configProfilesApi } from '../../api/configProfiles';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type {
  ConfigPresetItem,
  ConfigPresetPreviewResponse,
  ConfigProfileChange,
  ConfigProfileImportPreviewResponse,
} from '../../types/configProfiles';
import {
  ApiErrorAlert,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  FileInput,
  IconButton,
  StatePanel,
  Surface,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

export type ConfigPresetsPanelProps = {
  configVersion: string;
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
  onApplied: (updatedKeys: string[]) => Promise<void>;
};

function formatChangeLines(changes: ConfigProfileChange[]): string {
  if (!changes.length) {
    return '';
  }
  return changes
    .map((change) => {
      const from = change.fromValue === '' ? '∅' : change.fromValue;
      const to = change.to === '' ? '∅' : change.to;
      return `${change.key}: ${from} → ${to}`;
    })
    .join('\n');
}

const ConfigPresetsPanel: React.FC<ConfigPresetsPanelProps> = ({
  configVersion,
  disabled = false,
  t,
  language,
  onApplied,
}) => {
  void language;
  const importRef = useRef<HTMLInputElement | null>(null);

  const [presets, setPresets] = useState<ConfigPresetItem[]>([]);
  const [recommendedId, setRecommendedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState('');

  const [pendingPreset, setPendingPreset] = useState<ConfigPresetPreviewResponse | null>(null);
  const [pendingImport, setPendingImport] = useState<ConfigProfileImportPreviewResponse | null>(null);
  const [pendingImportContent, setPendingImportContent] = useState('');

  const loadPresets = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const payload = await configProfilesApi.listPresets();
      setPresets(payload.presets || []);
      setRecommendedId(payload.recommendedPresetId);
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error));
      setPresets([]);
      setRecommendedId(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPresets();
  }, [loadPresets]);

  const beginApplyPreset = async (presetId: string) => {
    setActionError(null);
    setSuccessMessage('');
    setIsBusy(true);
    try {
      const preview = await configProfilesApi.previewPreset(presetId, { configVersion });
      setPendingPreset(preview);
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const confirmApplyPreset = async () => {
    if (!pendingPreset) return;
    setIsBusy(true);
    setActionError(null);
    try {
      const result = await configProfilesApi.applyPreset(pendingPreset.presetId, {
        configVersion,
        reloadNow: true,
      });
      setPendingPreset(null);
      setSuccessMessage(result.message || t('settings.configPresetsApplied'));
      await onApplied(result.updatedKeys || []);
      await loadPresets();
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const exportProfile = async () => {
    setActionError(null);
    setSuccessMessage('');
    setIsBusy(true);
    try {
      const payload = await configProfilesApi.exportProfile();
      const blob = new Blob([payload.content], { type: 'text/yaml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = payload.filename || 'stockpulse-profile.yaml';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setSuccessMessage(
        t('settings.configPresetsExported', {
          count: payload.keysExported?.length ?? 0,
          redacted: payload.keysRedacted ?? 0,
        }),
      );
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const handleImportFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setActionError(null);
    setSuccessMessage('');
    setIsBusy(true);
    try {
      const content = await file.text();
      const preview = await configProfilesApi.previewImport({ configVersion, content });
      setPendingImport(preview);
      setPendingImportContent(content);
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
      setPendingImport(null);
      setPendingImportContent('');
    } finally {
      setIsBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!pendingImportContent) return;
    setIsBusy(true);
    setActionError(null);
    try {
      const result = await configProfilesApi.applyImport({
        configVersion,
        content: pendingImportContent,
        reloadNow: true,
      });
      setPendingImport(null);
      setPendingImportContent('');
      setSuccessMessage(result.message || t('settings.configPresetsImported'));
      await onApplied(result.updatedKeys || []);
      await loadPresets();
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const busy = disabled || isBusy || isLoading;
  const presetConfirmMessage = pendingPreset
    ? [
        pendingPreset.displayName,
        t('settings.configPresetsConfirmDescription', { count: pendingPreset.changeCount }),
        formatChangeLines(pendingPreset.changes || []),
      ].filter(Boolean).join('\n\n')
    : '';
  const importConfirmMessage = pendingImport
    ? [
        pendingImport.displayName || pendingImport.name,
        t('settings.configPresetsConfirmDescription', { count: pendingImport.changeCount }),
        formatChangeLines(pendingImport.changes || []),
      ].filter(Boolean).join('\n\n')
    : '';

  return (
    <>
      <SettingsSectionCard
        title={t('settings.configPresetsTitle')}
        description={t('settings.configPresetsDescription')}
        actions={(
          <IconButton
            type="button"
            variant="ghost"
            size="default"
            aria-label={t('settings.configPresetsRefreshAria')}
            disabled={busy}
            onClick={() => { void loadPresets(); }}
          >
            <RefreshCw size={16} />
          </IconButton>
        )}
      >
        <Surface className="space-y-4 p-4">
          <p className="text-sm text-secondary-text">
            {t('settings.configPresetsSecurityNote')}
          </p>

          {loadError ? <ApiErrorAlert error={loadError} /> : null}
          {actionError ? <ApiErrorAlert error={actionError} /> : null}
          {successMessage ? (
            <SettingsAlert variant="success" title={successMessage} message={successMessage} />
          ) : null}

          {isLoading ? (
            <StatePanel state="loading" title={t('settings.configPresetsLoading')} />
          ) : null}

          {!isLoading && presets.length === 0 && !loadError ? (
            <EmptyState
              title={t('settings.configPresetsEmptyTitle')}
              description={t('settings.configPresetsEmptyDescription')}
            />
          ) : null}

          <div className="space-y-3">
            {presets.map((preset) => {
              const isRecommended = preset.id === recommendedId || preset.recommended;
              return (
                <div
                  key={preset.id}
                  className="flex flex-col gap-2 rounded-lg border border-border p-3 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-primary-text">
                        {preset.displayName}
                      </span>
                      {isRecommended ? (
                        <Badge variant="success">{t('settings.configPresetsRecommended')}</Badge>
                      ) : null}
                      {!preset.meetsRequirements ? (
                        <Badge variant="warning">{t('settings.configPresetsRequirementsMissing')}</Badge>
                      ) : null}
                    </div>
                    <p className="text-sm text-secondary-text">
                      {preset.description}
                    </p>
                    {preset.tags?.length ? (
                      <p className="text-xs text-muted-text">
                        {preset.tags.join(' · ')}
                      </p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant={isRecommended ? 'primary' : 'secondary'}
                    size="compact"
                    disabled={busy}
                    onClick={() => { void beginApplyPreset(preset.id); }}
                  >
                    {t('settings.configPresetsApply')}
                  </Button>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Button
              type="button"
              variant="secondary"
              size="compact"
              disabled={busy}
              onClick={() => { void exportProfile(); }}
            >
              <Download size={14} className="mr-1" />
              {t('settings.configPresetsExport')}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="compact"
              disabled={busy}
              onClick={() => importRef.current?.click()}
            >
              <Upload size={14} className="mr-1" />
              {t('settings.configPresetsImport')}
            </Button>
            <FileInput
              ref={importRef}
              accept=".yaml,.yml,text/yaml,application/x-yaml,text/plain"
              onChange={(event) => { void handleImportFile(event); }}
            />
          </div>
        </Surface>
      </SettingsSectionCard>

      <ConfirmDialog
        isOpen={Boolean(pendingPreset)}
        title={t('settings.configPresetsConfirmTitle')}
        message={presetConfirmMessage}
        confirmText={t('settings.configPresetsConfirmApply')}
        cancelText={t('settings.configPresetsCancel')}
        confirmDisabled={isBusy}
        cancelDisabled={isBusy}
        onConfirm={() => { void confirmApplyPreset(); }}
        onCancel={() => setPendingPreset(null)}
      />

      <ConfirmDialog
        isOpen={Boolean(pendingImport)}
        title={t('settings.configPresetsImportConfirmTitle')}
        message={importConfirmMessage}
        confirmText={t('settings.configPresetsConfirmImport')}
        cancelText={t('settings.configPresetsCancel')}
        confirmDisabled={isBusy}
        cancelDisabled={isBusy}
        onConfirm={() => { void confirmImport(); }}
        onCancel={() => {
          setPendingImport(null);
          setPendingImportContent('');
        }}
      />
    </>
  );
};

export default ConfigPresetsPanel;
