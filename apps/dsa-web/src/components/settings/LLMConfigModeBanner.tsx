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

const SOURCE_LABEL: Record<string, { zh: string; en: string }> = {
  auto: { zh: '自动（兼容）', en: 'Auto (compatible)' },
  channels: { zh: 'Web 渠道', en: 'Web Channels' },
  yaml: { zh: 'YAML', en: 'YAML' },
  legacy: { zh: 'Legacy Provider', en: 'Legacy provider keys' },
};

interface LLMConfigModeBannerProps {
  status: LLMConfigModeStatus | null;
  configVersion?: string;
  onMigrated?: () => void;
}

export const LLMConfigModeBanner: React.FC<LLMConfigModeBannerProps> = ({ status, configVersion, onMigrated }) => {
  const { language } = useUiLanguage();
  const [preview, setPreview] = useState<LegacyChannelsMigrationPreview | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  if (!status) {
    return null;
  }

  const en = language === 'en';
  const label = (source: LLMConfigModeSource | null): string => {
    if (!source) {
      return en ? 'No model source configured' : '尚未配置模型来源';
    }
    return SOURCE_LABEL[source]?.[en ? 'en' : 'zh'] ?? source;
  };
  const overridden = status.overriddenSources
    .map((source) => SOURCE_LABEL[source]?.[en ? 'en' : 'zh'] ?? source)
    .join(en ? ', ' : '、');
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
          {en ? 'Effective model config source' : '当前生效模型配置来源'}
        </span>
        <Badge variant={status.effectiveMode ? 'success' : 'warning'} size="sm">
          {label(status.effectiveMode)}
        </Badge>
        {status.requestedMode !== 'auto' ? (
          <Badge variant="history" size="sm">
            {en ? `Requested: ${status.requestedMode}` : `请求模式：${status.requestedMode}`}
          </Badge>
        ) : null}
        {canMigrate ? (
          <Button
            type="button"
            variant="settings-secondary"
            size="xsm"
            className="ml-auto"
            isLoading={isLoadingPreview}
            onClick={() => void openPreview()}
          >
            {en ? 'Migrate to Channels' : '迁移到 Channels'}
          </Button>
        ) : null}
      </div>
      {overridden ? (
        <p className="mt-1.5 text-xs text-muted-text">
          {en
            ? `Present but overridden (not active): ${overridden}`
            : `已配置但被覆盖（不生效）：${overridden}`}
        </p>
      ) : null}
      {status.issues.length > 0 ? (
        <div className="mt-2 space-y-1">
          {status.issues.map((issue) => (
            <InlineAlert
              key={`${issue.code}-${issue.key}`}
              variant="warning"
              message={issue.message}
              className="rounded-lg px-3 py-2 text-xs shadow-none"
            />
          ))}
        </div>
      ) : null}
      {error && !isPreviewOpen ? <ApiErrorAlert className="mt-2" error={error} /> : null}

      <Modal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        title={en ? 'Migrate legacy providers to Channels' : '迁移旧版 Provider 到 Channels'}
      >
        <div className="space-y-3">
          <p className="text-xs text-muted-text">
            {en
              ? 'The following channels will be created from your legacy provider keys, and LLM_CONFIG_MODE will be set to channels. Legacy keys are kept.'
              : '将根据旧版 Provider 凭据创建以下渠道，并把 LLM_CONFIG_MODE 设为 channels。旧版 keys 会保留，不会删除。'}
          </p>
          <div className="overflow-hidden rounded-lg border border-[var(--settings-border)]">
            {(preview?.channels ?? []).map((channel) => (
              <div key={channel.name} className="flex flex-wrap items-center gap-2 border-b border-[var(--settings-border)] px-3 py-2 text-xs last:border-b-0">
                <span className="font-medium text-foreground">{channel.name}</span>
                <Badge variant="info" size="sm">{channel.protocol}</Badge>
                <span className="text-muted-text">{channel.model}</span>
                {channel.baseUrl ? <span className="text-muted-text">{channel.baseUrl}</span> : null}
              </div>
            ))}
          </div>
          {error ? <ApiErrorAlert error={error} /> : null}
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="settings-secondary" size="sm" onClick={() => setIsPreviewOpen(false)}>
              {en ? 'Cancel' : '取消'}
            </Button>
            <Button
              type="button"
              variant="settings-primary"
              size="sm"
              isLoading={isApplying}
              disabled={(preview?.channels ?? []).length === 0}
              onClick={() => void applyMigration()}
            >
              {en ? 'Migrate' : '确认迁移'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
