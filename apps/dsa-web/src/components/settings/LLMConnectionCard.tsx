import type React from 'react';
import { EllipsisVertical } from 'lucide-react';
import type { AvailableModelEntry, LlmProviderCatalogEntry } from '../../types/systemConfig';
import { Badge, Button, IconButton, Popover, StatusDot, Tooltip } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { MODEL_ACCESS_TEXT, localizeModelAccessIssue } from '../../locales/settingsModelAccess';
import { getProviderDisplayLabel } from './llmConnectionContract';
import { getUiListSeparator } from '../../utils/uiLocale';
import {
  findCatalogProvider,
  modelIdentityForConnection,
  resolveChannelRouteModels,
  splitModels,
  type ChannelConfig,
  type ChannelTestState,
  type TaskModelReference,
} from './llmChannelEditorModel';

interface ConnectionCardProps {
  channel: ChannelConfig;
  providers: LlmProviderCatalogEntry[];
  availableModels: AvailableModelEntry[];
  taskModelRefs: TaskModelReference[];
  unsaved: boolean;
  busy: boolean;
  testState?: ChannelTestState;
  issues: string[];
  onTest: () => void;
  canTest: boolean;
  onEdit: () => void;
  onManageModels: () => void;
  onToggleEnabled: () => void;
  canToggleEnabled: boolean;
  onRemove: () => void;
  canRemove: boolean;
}

// Compact connection card: provider, connection name, status, model chips and
// task usage plus quick actions. Credentials/endpoints/diagnostics live in the
// connection dialog, never on the card.
const ConnectionCard: React.FC<ConnectionCardProps> = ({
  channel,
  providers,
  availableModels,
  taskModelRefs,
  unsaved,
  busy,
  testState,
  issues,
  onTest,
  canTest,
  onEdit,
  onManageModels,
  onToggleEnabled,
  canToggleEnabled,
  onRemove,
  canRemove,
}) => {
  const { language } = useUiLanguage();
  const text = MODEL_ACCESS_TEXT[language];
  const provider = findCatalogProvider(providers, channel.providerId);
  const displayLabel = provider
    ? getProviderDisplayLabel(provider, language)
    : (channel.providerId && channel.providerId !== 'custom' ? channel.providerId : text.customProvider);
  const selectedModels = splitModels(channel.models);
  const channelRouteModels = resolveChannelRouteModels(channel);
  const channelModelRefs = new Set(channelRouteModels.map((route) => (
    modelIdentityForConnection(availableModels, channel.name, route)
  )));
  const usedByTasks = Array.from(
    new Set(
      taskModelRefs
        .filter((ref) => channelModelRefs.has(ref.route) || channelRouteModels.includes(ref.route))
        .map((ref) => ref.label),
    ),
  );
  const isComplete = issues.length === 0;
  const actionName = channel.displayName.trim() || channel.name;
  return (
    <div
      data-testid={`connection-card-${channel.name}`}
      className="rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-3 shadow-soft-card transition-[background-color,border-color] duration-200 hover:border-[var(--settings-border-strong)]"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          data-testid={`provider-avatar-${channel.providerId || 'custom'}`}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] text-sm font-semibold text-foreground"
        >
          {(displayLabel.trim()[0] || '?').toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">{displayLabel}</span>
            <span className="truncate text-xs text-muted-text">{channel.displayName}</span>
            {unsaved ? <Badge variant="warning">{text.unsaved}</Badge> : null}
            {!isComplete ? (
              <Tooltip content={issues.map((issue) => localizeModelAccessIssue(issue, language)).join(getUiListSeparator(language))}>
                <span className="inline-flex">
                  <Badge variant="warning">{text.incompleteDraft}</Badge>
                </span>
              </Tooltip>
            ) : null}
            <Badge variant={channel.enabled ? 'success' : 'default'}>
              {channel.enabled ? text.enabled : text.disabled}
            </Badge>
            {testState?.status === 'success' ? (
              <Badge variant="success">{text.testPassed}</Badge>
            ) : testState?.status === 'error' ? (
              <Badge variant="danger">{text.testFailed}</Badge>
            ) : testState?.status === 'loading' ? (
              <Badge variant="warning">{text.testing}</Badge>
            ) : (
              <Badge variant="default">{text.untested}</Badge>
            )}
          </div>
          {selectedModels.length > 0 ? (
            <button
              type="button"
              aria-label={formatUiText(text.manageModels, { name: actionName })}
              onClick={onManageModels}
              disabled={busy}
              className="mt-1.5 flex min-h-11 min-w-11 max-w-full flex-wrap items-center gap-1 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed"
              data-testid={`connection-models-${channel.id}`}
            >
              {selectedModels.slice(0, 4).map((model) => (
                <span
                  key={model}
                  className="max-w-48 truncate rounded-full border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-1.5 py-0.5 text-xs text-secondary-text"
                >
                  {model}
                </span>
              ))}
              {selectedModels.length > 4 ? (
                <span className="text-xs text-muted-text">+{selectedModels.length - 4}</span>
              ) : null}
            </button>
          ) : (
            <button
              type="button"
              aria-label={formatUiText(text.manageModels, { name: actionName })}
              onClick={onManageModels}
              disabled={busy}
              className="mt-1.5 inline-flex min-h-11 min-w-11 items-center rounded-lg text-left text-xs text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed"
            >
              {text.noModels}
            </button>
          )}
          {usedByTasks.length > 0 ? (
            <p className="mt-1 truncate text-xs text-muted-text">{formatUiText(text.usedBy, { tasks: usedByTasks.join(getUiListSeparator(language)) })}</p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            type="button"
            variant="secondary"
            size="default"
            className="text-xs shadow-none"
            disabled={busy || !canTest || testState?.status === 'loading'}
            onClick={onTest}
          >
            {testState?.status === 'loading' ? text.testing : text.test}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="default"
            className="text-xs shadow-none"
            disabled={busy}
            onClick={onEdit}
          >
            {text.edit}
          </Button>
          <Popover
            contentRole="menu"
            placement="bottom"
            align="end"
            contentClassName="w-36 p-1"
            trigger={({ open, toggle }) => (
              <IconButton
                type="button"
                variant="ghost"
                size="default"
                className="text-muted-text"
                disabled={busy}
                aria-label={formatUiText(text.moreActions, { name: actionName })}
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={toggle}
              >
                <EllipsisVertical aria-hidden="true" />
              </IconButton>
            )}
          >
            {({ close }) => (
              <>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!canToggleEnabled}
                  className="flex min-h-11 w-full items-center rounded-lg px-3 py-1.5 text-left text-xs text-foreground hover:bg-hover"
                  onClick={() => {
                    if (!canToggleEnabled) {
                      return;
                    }
                    close();
                    onToggleEnabled();
                  }}
                >
                  {channel.enabled ? text.disableConnection : text.enableConnection}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!canRemove}
                  className="flex min-h-11 w-full items-center rounded-lg px-3 py-1.5 text-left text-xs text-danger hover:bg-hover"
                  onClick={() => {
                    if (!canRemove) {
                      return;
                    }
                    close();
                    onRemove();
                  }}
                >
                  {text.deleteConnection}
                </button>
              </>
            )}
          </Popover>
        </div>
      </div>

      {testState?.text ? (
        <div className="mt-2 flex items-start gap-1.5">
          <span className="mt-0.5 inline-flex">
            <StatusDot
              tone={testState.status === 'success' ? 'success' : testState.status === 'error' ? 'danger' : 'warning'}
              pulse={testState.status === 'loading'}
            />
          </span>
          <div className="min-w-0">
            <p className={`text-xs ${testState.status === 'success' ? 'text-success' : testState.status === 'error' ? 'text-danger' : 'text-muted-text'}`}>
              {testState.text}
            </p>
            {testState.hint ? <p className="text-xs text-secondary-text">{testState.hint}</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default ConnectionCard;
