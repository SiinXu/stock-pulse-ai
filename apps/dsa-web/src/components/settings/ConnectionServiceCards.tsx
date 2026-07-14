import type React from 'react';
import { Badge, Button } from '../common';
import type { ConnectionCard, ConnectionStatus } from './connectionModel';
import type { UiLang } from './settingsInformationArchitecture';

interface ConnectionServiceCardsProps {
  connections: ConnectionCard[];
  language: UiLang;
  onAddService: () => void;
  addDisabled?: boolean;
}

const STATUS_META: Record<ConnectionStatus, { zh: string; en: string; variant: 'success' | 'warning' | 'default' }> = {
  configured: { zh: '已配置', en: 'Configured', variant: 'success' },
  incomplete: { zh: '未完成', en: 'Incomplete', variant: 'warning' },
  disabled: { zh: '已停用', en: 'Disabled', variant: 'default' },
};

/**
 * Read-only "model access" overview: one card per configured connection with its
 * provider, status, model count and which tasks use it. The everyday path uses
 * "Add model service" (not "add channel") and never surfaces channel/route-alias
 * jargon.
 */
export const ConnectionServiceCards: React.FC<ConnectionServiceCardsProps> = ({
  connections,
  language,
  onAddService,
  addDisabled = false,
}) => {
  const tx = (zh: string, en: string) => (language === 'en' ? en : zh);
  return (
    <div className="space-y-3" data-testid="model-access-service-cards">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-secondary-text">
          {connections.length > 0
            ? tx(`已接入 ${connections.length} 个模型服务`, `${connections.length} model service${connections.length > 1 ? 's' : ''} connected`)
            : tx('尚未接入模型服务', 'No model services connected yet')}
        </p>
        <Button type="button" variant="settings-primary" size="sm" onClick={onAddService} disabled={addDisabled}>
          {tx('添加模型服务', 'Add model service')}
        </Button>
      </div>

      {connections.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--settings-border)] px-4 py-6 text-center text-xs text-muted-text">
          {tx('点击「添加模型服务」，选择服务商并填写凭据即可开始。', 'Click "Add model service", pick a provider and enter its credentials to begin.')}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {connections.map((connection) => {
            const status = STATUS_META[connection.status];
            return (
              <div
                key={connection.name}
                data-testid={`model-access-card-${connection.name}`}
                className="rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">{connection.providerLabel}</p>
                    <p className="truncate text-xs text-muted-text">{connection.name}</p>
                  </div>
                  <Badge variant={status.variant} size="sm">{tx(status.zh, status.en)}</Badge>
                </div>
                <dl className="mt-2 space-y-1 text-xs text-secondary-text">
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-text">{tx('可用模型', 'Available models')}</dt>
                    <dd className="font-medium text-foreground">{connection.modelCount}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-text">{tx('被以下任务使用', 'Used by tasks')}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">
                      {connection.usedByTasks.length > 0
                        ? connection.usedByTasks.join(tx('、', ', '))
                        : tx('未被使用', 'none')}
                    </dd>
                  </div>
                </dl>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
