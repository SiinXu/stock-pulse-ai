// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useState } from 'react';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  LegacyChannelsMigrationPreview,
  LLMConfigModeSource,
  LLMConfigModeStatus,
} from '../../types/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { ApiErrorAlert, Badge, Button, InlineAlert, Modal } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_CONTROLS_TEXT, SETTINGS_SOURCE_LABELS } from '../../locales/settingsControls';
import { getUiListSeparator } from '../../utils/uiLocale';

interface LLMConfigModeBannerProps {
  status: LLMConfigModeStatus | null;
  configVersion?: string;
  onMigrated?: () => void;
}

export const LLMConfigModeBanner: React.FC<LLMConfigModeBannerProps> = ({ status, configVersion, onMigrated }) => {
  const { language } = useUiLanguage();
  const text = SETTINGS_CONTROLS_TEXT[language];
  const [preview, setPreview] = useState<LegacyChannelsMigrationPreview | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  if (!status) {
    return null;
  }

  const label = (source: LLMConfigModeSource | null): string => {
    if (!source) {
      return text.noModelSource;
    }
    return SETTINGS_SOURCE_LABELS[language][source] ?? source;
  };
  const overridden = status.overriddenSources
    .map((source) => SETTINGS_SOURCE_LABELS[language][source] ?? source)
    .join(getUiListSeparator(language));
  const canMigrate = Boolean(configVersion) && status.detectedSources.includes('legacy') && status.effectiveMode !== 'channels';

  const openPreview = async () => {
    setError(null);
    setIsLoadingPreview(true);
    try {
      setPreview(await systemConfigApi.previewLegacyChannelsMigration());
      setIsPreviewOpen(true);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const applyMigration = async () => {
    if (!configVersion) {
      return;
    }
    setError(null);
    setIsApplying(true);
    try {
      await systemConfigApi.applyLegacyChannelsMigration(configVersion);
      setIsPreviewOpen(false);
      onMigrated?.();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div className="rounded-xl border settings-border bg-card/70 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">
          {text.effectiveSource}
        </span>
        <Badge variant={status.effectiveMode ? 'success' : 'warning'} size="sm">
          {label(status.effectiveMode)}
        </Badge>
        {status.requestedMode !== 'auto' ? (
          <Badge variant="default" size="sm">
            {formatUiText(text.requestedMode, { mode: status.requestedMode })}
          </Badge>
        ) : null}
        {canMigrate ? (
          <Button
            type="button"
            variant="secondary"
            size="xsm"
            className="ml-auto"
            isLoading={isLoadingPreview}
            onClick={() => void openPreview()}
          >
            {text.migrateToChannels}
          </Button>
        ) : null}
      </div>
      {overridden ? (
        <p className="mt-1.5 text-xs text-muted-text">
          {formatUiText(text.overriddenSources, { sources: overridden })}
        </p>
      ) : null}
      {status.issues.length > 0 ? (
        <div className="mt-2 space-y-1">
          {status.issues.map((issue) => (
            <InlineAlert
              key={`${issue.code}-${issue.key}`}
              variant="warning"
              message={issue.code === 'forced_mode_no_config'
                ? formatUiText(text.configModeIssue, { mode: status.requestedMode })
                : text.unknownConfigIssue}
              className="rounded-lg px-3 py-2 text-xs shadow-none"
            />
          ))}
        </div>
      ) : null}
      {error && !isPreviewOpen ? <ApiErrorAlert className="mt-2" error={error} /> : null}

      <Modal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        title={text.migrationTitle}
      >
        <div className="space-y-3">
          <p className="text-xs text-muted-text">
            {text.migrationDescription}
          </p>
          <div className="overflow-hidden rounded-lg border border-[var(--settings-border)]">
            {(preview?.channels ?? []).map((channel) => (
              <div key={channel.name} className="flex flex-wrap items-center gap-2 border-b border-[var(--settings-border)] px-3 py-2 text-xs last:border-b-0">
                <span className="font-medium text-foreground">{channel.name}</span>
                <Badge variant="default" size="sm">{channel.protocol}</Badge>
                <span className="text-muted-text">{channel.model}</span>
                {channel.baseUrl ? <span className="text-muted-text">{channel.baseUrl}</span> : null}
              </div>
            ))}
          </div>
          {error ? <ApiErrorAlert error={error} /> : null}
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => setIsPreviewOpen(false)}>
              {text.cancel}
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              isLoading={isApplying}
              disabled={(preview?.channels ?? []).length === 0}
              onClick={() => void applyMigration()}
            >
              {text.migrate}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
