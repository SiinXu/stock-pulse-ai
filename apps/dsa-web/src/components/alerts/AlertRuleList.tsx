import type React from 'react';
import { useState } from 'react';
import { Bell, Trash2 } from 'lucide-react';
import { Badge, Button, Card, ConfirmDialog, DataTable, type DataTableColumn, Pagination, Select } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import {
  ALERT_DIRECTION_LABELS,
  ALERT_ENABLED_FILTER_OPTIONS,
  ALERT_LIST_TEXT,
  ALERT_MARKET_LIGHT_STATUS_LABELS,
  ALERT_MARKET_REGION_LABELS,
  ALERT_SCOPE_LABELS,
  ALERT_SEVERITY_LABELS,
  ALERT_TYPE_FILTER_OPTIONS,
  ALERT_TYPE_LABELS,
} from '../../locales/alerts';
import type { AlertRuleItem, AlertType, MarketRegion } from '../../types/alerts';
import { formatUiDateTime } from '../../utils/uiLocale';

export type AlertRuleEnabledFilter = 'all' | 'enabled' | 'disabled';
export type AlertTypeFilter = 'all' | AlertType;
export type AlertRuleBusyAction = 'test' | 'toggle' | 'delete';
export type AlertRuleBusyMap = Readonly<Record<number, AlertRuleBusyAction | undefined>>;

function formatParameters(rule: AlertRuleItem, language: UiLanguage): string {
  const directionLabels = ALERT_DIRECTION_LABELS[language];
  if (rule.alertType === 'market_light_status') {
    const statuses = rule.parameters.statuses ?? [];
    return statuses.length > 0
      ? statuses.map((status) => ALERT_MARKET_LIGHT_STATUS_LABELS[language][status] ?? status).join(' / ')
      : '--';
  }
  if (rule.alertType === 'market_light_score_drop') {
    return formatUiText(ALERT_LIST_TEXT[language].scoreDropAtLeast, { value: rule.parameters.minDrop ?? '--' });
  }
  if (rule.alertType === 'price_cross') {
    return `${rule.parameters.direction === 'below' ? directionLabels.belowPrice : directionLabels.abovePrice} ${rule.parameters.price ?? '--'}`;
  }
  if (rule.alertType === 'price_change_percent') {
    return `${rule.parameters.direction === 'down' ? directionLabels.downChange : directionLabels.upChange} ${rule.parameters.changePct ?? '--'}%`;
  }
  if (rule.alertType === 'volume_spike') {
    return `${rule.parameters.multiplier ?? '--'}x`;
  }
  if (rule.alertType === 'ma_price_cross') {
    return `${rule.parameters.direction === 'below' ? directionLabels.belowThreshold : directionLabels.aboveThreshold} MA${rule.parameters.window ?? '--'}`;
  }
  if (rule.alertType === 'rsi_threshold') {
    return `RSI${rule.parameters.period ?? '--'} ${rule.parameters.direction === 'below' ? directionLabels.belowThreshold : directionLabels.aboveThreshold} ${rule.parameters.threshold ?? '--'}`;
  }
  if (rule.alertType === 'macd_cross' || rule.alertType === 'kdj_cross') {
    const direction = rule.parameters.direction === 'bearish_cross' ? directionLabels.bearishCross : directionLabels.bullishCross;
    if (rule.alertType === 'macd_cross') {
      return `MACD(${rule.parameters.fastPeriod ?? '--'},${rule.parameters.slowPeriod ?? '--'},${rule.parameters.signalPeriod ?? '--'}) ${direction}`;
    }
    return `KDJ(${rule.parameters.period ?? '--'},${rule.parameters.kPeriod ?? '--'},${rule.parameters.dPeriod ?? '--'}) ${direction}`;
  }
  if (rule.alertType === 'portfolio_stop_loss') {
    return rule.parameters.mode === 'breach' ? directionLabels.stopLossBreach : directionLabels.stopLossNear;
  }
  if (rule.alertType === 'portfolio_concentration') return 'top_weight_pct';
  if (rule.alertType === 'portfolio_drawdown') return 'max_drawdown_pct';
  if (rule.alertType === 'portfolio_price_stale') return 'price_stale / price_available';
  return `CCI${rule.parameters.period ?? '--'} ${rule.parameters.direction === 'below' ? directionLabels.belowThreshold : directionLabels.aboveThreshold} ${rule.parameters.threshold ?? '--'}`;
}

function isCoolingDown(rule: AlertRuleItem): boolean {
  return rule.cooldownActive === true;
}

function formatTarget(rule: AlertRuleItem, language: UiLanguage): string {
  if (rule.targetScope === 'market') return ALERT_MARKET_REGION_LABELS[language][rule.target as MarketRegion] ?? rule.target;
  if (rule.targetScope === 'watchlist') return 'default';
  if (rule.targetScope === 'portfolio_account' || rule.targetScope === 'portfolio_holdings') {
    const text = ALERT_LIST_TEXT[language];
    return rule.target === 'all'
      ? text.allAccounts
      : formatUiText(text.accountTarget, { target: rule.target });
  }
  return rule.target;
}

function hasChildTargetCooldown(rule: AlertRuleItem): boolean {
  return rule.targetScope === 'watchlist' || rule.targetScope === 'portfolio_holdings';
}

interface AlertRuleListProps {
  rules: AlertRuleItem[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  enabledFilter: AlertRuleEnabledFilter;
  alertTypeFilter: AlertTypeFilter;
  onEnabledFilterChange: (value: AlertRuleEnabledFilter) => void;
  onAlertTypeFilterChange: (value: AlertTypeFilter) => void;
  onPageChange: (page: number) => void;
  onToggleEnabled: (rule: AlertRuleItem) => void;
  onDelete: (rule: AlertRuleItem) => void;
  onEdit: (rule: AlertRuleItem) => void;
  onTest: (rule: AlertRuleItem) => void;
  busyRules?: AlertRuleBusyMap;
}

export const AlertRuleList: React.FC<AlertRuleListProps> = ({
  rules,
  total,
  page,
  pageSize,
  isLoading = false,
  enabledFilter,
  alertTypeFilter,
  onEnabledFilterChange,
  onAlertTypeFilterChange,
  onPageChange,
  onToggleEnabled,
  onDelete,
  onEdit,
  onTest,
  busyRules = {},
}) => {
  const { language } = useUiLanguage();
  const text = ALERT_LIST_TEXT[language];
  const [pendingDelete, setPendingDelete] = useState<AlertRuleItem | null>(null);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const isRuleBusy = (rule: AlertRuleItem) => Boolean(busyRules[rule.id]);
  const isRuleActionBusy = (rule: AlertRuleItem, action: AlertRuleBusyAction) => (
    busyRules[rule.id] === action
  );

  const ruleColumns: DataTableColumn<AlertRuleItem>[] = [
    {
      id: 'rule',
      header: text.rule,
      cell: (rule) => (
        <>
          <div className="font-medium text-foreground">{rule.name}</div>
          <div className="mt-1 text-xs text-muted-text">{formatUiText(text.source, { source: rule.source })}</div>
        </>
      ),
    },
    {
      id: 'target',
      header: text.target,
      cell: (rule) => (
        <>
          <div className="font-mono">{formatTarget(rule, language)}</div>
          <div className="mt-1 text-xs">{ALERT_SCOPE_LABELS[language][rule.targetScope] ?? rule.targetScope}</div>
        </>
      ),
    },
    {
      id: 'type',
      header: text.type,
      cell: (rule) => (
        <div className="flex flex-col items-start gap-1">
          <Badge variant="info">{ALERT_TYPE_LABELS[language][rule.alertType]}</Badge>
          <Badge variant={rule.severity === 'critical' ? 'danger' : rule.severity === 'warning' ? 'warning' : 'default'}>
            {ALERT_SEVERITY_LABELS[language][rule.severity] ?? rule.severity}
          </Badge>
        </div>
      ),
    },
    {
      id: 'parameters',
      header: text.parameters,
      cell: (rule) => formatParameters(rule, language),
    },
    {
      id: 'status',
      header: text.status,
      cell: (rule) => (
        <Badge variant={rule.enabled ? 'success' : 'default'}>
          {rule.enabled ? text.enabled : text.disabled}
        </Badge>
      ),
    },
    {
      id: 'cooldown',
      header: text.cooldown,
      cell: (rule) => (
        <div className="text-xs">
          <div>{isCoolingDown(rule) ? text.coolingDown : text.notCoolingDown}</div>
          <div className="mt-1">{formatUiDateTime(rule.cooldownUntil, language, { dateStyle: 'medium', timeStyle: 'short' })}</div>
          {hasChildTargetCooldown(rule) ? (
            <div className="mt-1 text-muted-text">{text.childTargetCooldown}</div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'updatedAt',
      header: text.updatedAt,
      cell: (rule) => (
        <span className="text-xs">
          {formatUiDateTime(rule.updatedAt ?? rule.createdAt, language, { dateStyle: 'medium', timeStyle: 'short' })}
        </span>
      ),
    },
    {
      id: 'action',
      header: text.action,
      align: 'end',
      cell: (rule) => (
        <div className="flex justify-end gap-2">
          <Button
            size="compact"
            variant="outline"
            aria-label={formatUiText(text.editAria, { name: rule.name })}
            onClick={() => onEdit(rule)}
            disabled={isLoading || isRuleBusy(rule)}
          >
            {text.edit}
          </Button>
          <Button
            size="compact"
            variant="outline"
            onClick={() => onTest(rule)}
            isLoading={isRuleActionBusy(rule, 'test')}
            loadingText={text.testing}
            disabled={isLoading || (isRuleBusy(rule) && !isRuleActionBusy(rule, 'test'))}
          >
            {text.test}
          </Button>
          <Button
            size="compact"
            variant={rule.enabled ? 'secondary' : 'primary'}
            onClick={() => onToggleEnabled(rule)}
            isLoading={isRuleActionBusy(rule, 'toggle')}
            loadingText={rule.enabled ? text.disabling : text.enabling}
            disabled={isLoading || (isRuleBusy(rule) && !isRuleActionBusy(rule, 'toggle'))}
          >
            {rule.enabled ? text.disable : text.enable}
          </Button>
          <Button
            size="compact"
            variant="danger-subtle"
            aria-label={formatUiText(text.deleteAria, { name: rule.name })}
            onClick={() => setPendingDelete(rule)}
            disabled={isLoading || isRuleBusy(rule)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {text.delete}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Card
      title={text.title}
      subtitle={formatUiText(text.subtitle, { total })}
      headerRight={(
        <div className="grid w-full max-w-full items-end gap-2 sm:flex sm:w-auto sm:flex-wrap sm:justify-end">
          <Select
            ariaLabel={text.enabledFilter}
            value={enabledFilter}
            options={ALERT_ENABLED_FILTER_OPTIONS[language]}
            onChange={(value) => {
              onEnabledFilterChange(value as AlertRuleEnabledFilter);
            }}
            className="w-full sm:w-32"
          />
          <Select
            ariaLabel={text.alertTypeFilter}
            value={alertTypeFilter}
            options={ALERT_TYPE_FILTER_OPTIONS[language]}
            onChange={(value) => {
              onAlertTypeFilterChange(value as AlertTypeFilter);
            }}
            className="w-full max-w-full sm:w-44"
          />
        </div>
      )}
      variant="bordered"
      padding="md"
      className="flex flex-col [&>div:first-child]:flex-col [&>div:first-child]:items-stretch sm:[&>div:first-child]:flex-row sm:[&>div:first-child]:items-start"
    >
      <div
        className={`relative min-h-0 flex-1 ${isLoading && rules.length > 0 ? 'pointer-events-none opacity-60' : ''}`}
        aria-busy={isLoading || undefined}
      >
        <DataTable<AlertRuleItem>
          caption={text.title}
          columns={ruleColumns}
          rows={rules}
          getRowKey={(rule) => rule.id}
          emptyState={{
            icon: <Bell className="h-6 w-6" />,
            title: isLoading ? text.loadingRules : text.emptyTitle,
            description: text.emptyDescription,
          }}
          density="compact"
          minWidth="extra-wide"
        />
      </div>

      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={onPageChange}
        className="mt-5"
      />

      <ConfirmDialog
        isOpen={pendingDelete != null}
        title={text.deleteTitle}
        message={pendingDelete ? formatUiText(text.deleteMessage, { name: pendingDelete.name }) : ''}
        confirmText={text.delete}
        cancelText={text.cancel}
        isDanger
        onConfirm={() => {
          if (pendingDelete) {
            onDelete(pendingDelete);
          }
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </Card>
  );
};
