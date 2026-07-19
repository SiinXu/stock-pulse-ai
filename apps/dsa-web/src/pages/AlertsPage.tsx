import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BellRing, RefreshCw } from 'lucide-react';
import { alertsApi } from '../api/alerts';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { AlertRuleForm } from '../components/alerts/AlertRuleForm';
import {
  AlertRuleList,
  type AlertRuleBusyAction,
  type AlertRuleBusyMap,
  type AlertRuleEnabledFilter,
  type AlertTypeFilter,
} from '../components/alerts/AlertRuleList';
import { AlertTriggerHistory } from '../components/alerts/AlertTriggerHistory';
import { ApiErrorAlert, AppPage, Button, Card, DataTable, InlineAlert, Modal, PageHeader, Pagination, SegmentedControl, Select, StatePanel, Toolbar, type DataTableColumn } from '../components/common';
import type {
  AlertNotificationItem,
  AlertRuleCreateRequest,
  AlertRuleItem,
  AlertRuleTestResponse,
  AlertTriggerItem,
  AlertType,
} from '../types/alerts';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText, type UiLanguage } from '../i18n/uiText';
import {
  ALERT_NOTIFICATION_CHANNEL_LABELS,
  ALERT_NOTIFICATION_STATUS_LABELS,
  ALERT_HISTORY_CONTROLS_TEXT,
  ALERT_LIST_TEXT,
  ALERT_PAGE_TEXT,
  ALERT_TRIGGER_TEXT,
} from '../locales/alerts';
import { formatUiDateTime } from '../utils/uiLocale';

const PAGE_SIZE = 20;
type AlertsView = 'rules' | 'history' | 'notifications';

function enabledFilterToQuery(value: AlertRuleEnabledFilter): boolean | undefined {
  if (value === 'enabled') return true;
  if (value === 'disabled') return false;
  return undefined;
}

function alertTypeFilterToQuery(value: AlertTypeFilter): AlertType | undefined {
  return value === 'all' ? undefined : value;
}

function testVariant(result: AlertRuleTestResponse): 'success' | 'warning' | 'danger' {
  if (result.status === 'evaluation_error') return 'danger';
  return result.triggered ? 'success' : 'warning';
}

function renderTestResultMessage(result: AlertRuleTestResponse, language: UiLanguage): React.ReactNode {
  const text = ALERT_PAGE_TEXT[language];
  const controlsText = ALERT_HISTORY_CONTROLS_TEXT[language];
  const triggerText = ALERT_TRIGGER_TEXT[language];
  const targetResults = result.targetResults ?? [];
  return (
    <div className="space-y-2">
      <div>
        {result.message}
        {` · ${text.status}: `}
        {controlsText.testStatuses[result.status] ?? result.status}
        {` · ${text.triggered}: `}
        {result.triggered ? text.yes : text.no}
        {` · ${text.observed}: `}
        {result.observedValue == null ? '--' : String(result.observedValue)}
      </div>
      {result.evaluatedCount != null && result.evaluatedCount > 1 ? (
        <div className="text-xs">
          {formatUiText(text.evaluationSummary, { evaluated: result.evaluatedCount, triggered: result.triggeredCount ?? 0, degraded: result.degradedCount ?? 0, skipped: result.skippedCount ?? 0 })}
        </div>
      ) : null}
      {targetResults.length > 1 ? (
        <div className="grid gap-1 text-xs">
          {targetResults.slice(0, 20).map((item) => (
            <div key={`${item.target}-${item.status}`} className="flex flex-wrap justify-between gap-2">
              <span>{item.displayTarget ?? item.target}</span>
              <span>
                {controlsText.testStatuses[item.status] ?? item.status}
                {item.recordStatus ? ` / ${triggerText.statuses[item.recordStatus] ?? item.recordStatus}` : ''}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatNotificationChannel(channel: string, language: UiLanguage): string {
  return ALERT_NOTIFICATION_CHANNEL_LABELS[language][channel] ?? channel;
}

function formatNotificationStatus(notification: AlertNotificationItem, language: UiLanguage): string {
  const labels = ALERT_NOTIFICATION_STATUS_LABELS[language];
  if (notification.success) return labels.success;
  return (notification.errorCode && labels[notification.errorCode]) || labels.failure;
}

const AlertsPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const text = ALERT_PAGE_TEXT[language];
  const controlsText = ALERT_HISTORY_CONTROLS_TEXT[language];
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const [createRuleModalOpen, setCreateRuleModalOpen] = useState(false);
  const [activeView, setActiveView] = useState<AlertsView>('rules');
  const [rules, setRules] = useState<AlertRuleItem[]>([]);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [rulesPage, setRulesPage] = useState(1);
  const [enabledFilter, setEnabledFilter] = useState<AlertRuleEnabledFilter>('all');
  const [alertTypeFilter, setAlertTypeFilter] = useState<AlertTypeFilter>('all');
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<ParsedApiError | null>(null);
  const [rulesLoaded, setRulesLoaded] = useState(false);

  const [triggers, setTriggers] = useState<AlertTriggerItem[]>([]);
  const [triggersPage, setTriggersPage] = useState(1);
  const [triggersTotal, setTriggersTotal] = useState(0);
  const [triggersLastUpdated, setTriggersLastUpdated] = useState<string | null>(null);
  const [triggersLoading, setTriggersLoading] = useState(false);
  const [triggersError, setTriggersError] = useState<ParsedApiError | null>(null);

  const [notifications, setNotifications] = useState<AlertNotificationItem[]>([]);
  const [notificationsPage, setNotificationsPage] = useState(1);
  const [notificationsTotal, setNotificationsTotal] = useState(0);
  const [notificationsLastUpdated, setNotificationsLastUpdated] = useState<string | null>(null);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<ParsedApiError | null>(null);
  const [notificationChannelFilter, setNotificationChannelFilter] = useState('all');
  const [notificationSuccessFilter, setNotificationSuccessFilter] = useState<'all' | 'success' | 'failure'>('all');

  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<ParsedApiError | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [busyRules, setBusyRules] = useState<AlertRuleBusyMap>({});
  const [testResult, setTestResult] = useState<{
    ruleId: number;
    ruleName: string;
    response: AlertRuleTestResponse;
  } | null>(null);
  const rulesRequestIdRef = useRef(0);
  const triggersRequestIdRef = useRef(0);
  const notificationsRequestIdRef = useRef(0);
  const busyRulesRef = useRef<Map<number, AlertRuleBusyAction>>(new Map());
  const mountedRef = useRef(true);

  const notificationColumns = useMemo<DataTableColumn<AlertNotificationItem>[]>(() => [
    {
      id: 'channel',
      header: text.channel,
      cell: (notification) => formatNotificationChannel(notification.channel, language),
    },
    {
      id: 'status',
      header: text.status,
      cell: (notification) => formatNotificationStatus(notification, language),
    },
    {
      id: 'errorCode',
      header: text.errorCode,
      cell: (notification) => notification.errorCode ?? '--',
      priority: 'secondary',
    },
    {
      id: 'latency',
      header: text.latency,
      cell: (notification) => notification.latencyMs == null ? '--' : `${notification.latencyMs}ms`,
      priority: 'tertiary',
    },
    {
      id: 'time',
      header: text.time,
      cell: (notification) => formatUiDateTime(notification.createdAt, language, { dateStyle: 'medium', timeStyle: 'short' }),
      cellClassName: 'whitespace-nowrap',
    },
    {
      id: 'diagnostics',
      header: text.diagnostics,
      cell: (notification) => notification.diagnostics ?? '--',
      priority: 'tertiary',
      cellClassName: 'max-w-80 break-words',
    },
  ], [language, text]);

  const beginRuleOperation = useCallback((ruleId: number, action: AlertRuleBusyAction): boolean => {
    if (busyRulesRef.current.has(ruleId)) return false;
    busyRulesRef.current.set(ruleId, action);
    setBusyRules(Object.fromEntries(busyRulesRef.current));
    return true;
  }, []);

  const finishRuleOperation = useCallback((ruleId: number, action: AlertRuleBusyAction): void => {
    if (busyRulesRef.current.get(ruleId) !== action) return;
    busyRulesRef.current.delete(ruleId);
    if (mountedRef.current) setBusyRules(Object.fromEntries(busyRulesRef.current));
  }, []);

  const loadRules = useCallback(async (pageOverride?: number) => {
    const requestId = rulesRequestIdRef.current + 1;
    rulesRequestIdRef.current = requestId;
    const isLatestRequest = () => rulesRequestIdRef.current === requestId;
    const requestedPage = pageOverride ?? rulesPage;
    const baseQuery = {
      enabled: enabledFilterToQuery(enabledFilter),
      alertType: alertTypeFilterToQuery(alertTypeFilter),
      pageSize: PAGE_SIZE,
    };
    setRulesLoading(true);
    try {
      let response = await alertsApi.listRules({ ...baseQuery, page: requestedPage });
      if (!isLatestRequest()) return null;
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (response.items.length === 0 && response.total > 0 && requestedPage > lastPage) {
        setRulesPage(lastPage);
        response = await alertsApi.listRules({ ...baseQuery, page: lastPage });
        if (!isLatestRequest()) return null;
      } else if (pageOverride !== undefined && pageOverride !== rulesPage) {
        setRulesPage(pageOverride);
      }
      setRules(response.items);
      setRulesTotal(response.total);
      setRulesError(null);
      setRulesLoaded(true);
      return response;
    } catch (error) {
      if (!isLatestRequest()) return null;
      setRulesError(getParsedApiError(error));
      return null;
    } finally {
      if (isLatestRequest()) {
        setRulesLoading(false);
      }
    }
  }, [alertTypeFilter, enabledFilter, rulesPage]);

  const loadTriggers = useCallback(async (page = 1) => {
    const requestId = triggersRequestIdRef.current + 1;
    triggersRequestIdRef.current = requestId;
    const isLatestRequest = () => triggersRequestIdRef.current === requestId;
    setTriggersLoading(true);
    setTriggersError(null);
    try {
      const response = await alertsApi.listTriggers({ page, pageSize: PAGE_SIZE });
      if (!isLatestRequest()) return;
      setTriggers(response.items);
      setTriggersTotal(response.total);
      setTriggersPage(response.page);
      setTriggersLastUpdated(new Date().toISOString());
    } catch (error) {
      if (!isLatestRequest()) return;
      setTriggersError(getParsedApiError(error));
    } finally {
      if (isLatestRequest()) setTriggersLoading(false);
    }
  }, []);

  const loadNotifications = useCallback(async (page = 1) => {
    const requestId = notificationsRequestIdRef.current + 1;
    notificationsRequestIdRef.current = requestId;
    const isLatestRequest = () => notificationsRequestIdRef.current === requestId;
    setNotificationsLoading(true);
    setNotificationsError(null);
    try {
      const response = await alertsApi.listNotifications({
        ...(notificationChannelFilter === 'all' ? {} : { channel: notificationChannelFilter }),
        ...(notificationSuccessFilter === 'all' ? {} : { success: notificationSuccessFilter === 'success' }),
        page,
        pageSize: PAGE_SIZE,
      });
      if (!isLatestRequest()) return;
      setNotifications(response.items);
      setNotificationsTotal(response.total);
      setNotificationsPage(response.page);
      setNotificationsLastUpdated(new Date().toISOString());
    } catch (error) {
      if (!isLatestRequest()) return;
      setNotificationsError(getParsedApiError(error));
    } finally {
      if (isLatestRequest()) setNotificationsLoading(false);
    }
  }, [notificationChannelFilter, notificationSuccessFilter]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      rulesRequestIdRef.current += 1;
      triggersRequestIdRef.current += 1;
      notificationsRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  useEffect(() => {
    if (!rulesLoaded) return;
    void loadTriggers(triggersPage);
  }, [loadTriggers, rulesLoaded, triggersPage]);

  useEffect(() => {
    if (!rulesLoaded) return;
    void loadNotifications(notificationsPage);
  }, [loadNotifications, notificationsPage, rulesLoaded]);

  const handleCreateRule = async (payload: AlertRuleCreateRequest) => {
    setCreateLoading(true);
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await alertsApi.createRule(payload);
      if (!mountedRef.current) return false;
      setCreateSuccess(formatUiText(text.created, { name: created.name }));
      await loadRules(1);
      return true;
    } catch (error) {
      if (mountedRef.current) setCreateError(getParsedApiError(error));
      return false;
    } finally {
      if (mountedRef.current) setCreateLoading(false);
    }
  };

  const handleToggleEnabled = async (rule: AlertRuleItem) => {
    if (!beginRuleOperation(rule.id, 'toggle')) return;
    try {
      if (rule.enabled) {
        await alertsApi.disableRule(rule.id);
      } else {
        await alertsApi.enableRule(rule.id);
      }
      if (mountedRef.current) await loadRules();
    } catch (error) {
      if (mountedRef.current) setRulesError(getParsedApiError(error));
    } finally {
      finishRuleOperation(rule.id, 'toggle');
    }
  };

  const handleDeleteRule = async (rule: AlertRuleItem) => {
    if (!beginRuleOperation(rule.id, 'delete')) return;
    try {
      await alertsApi.deleteRule(rule.id);
      if (mountedRef.current) await loadRules();
    } catch (error) {
      if (mountedRef.current) setRulesError(getParsedApiError(error));
    } finally {
      finishRuleOperation(rule.id, 'delete');
    }
  };

  const handleTestRule = async (rule: AlertRuleItem) => {
    if (!beginRuleOperation(rule.id, 'test')) return;
    setTestResult(null);
    try {
      const result = await alertsApi.testRule(rule.id);
      if (mountedRef.current) {
        setTestResult({ ruleId: rule.id, ruleName: rule.name, response: result });
        void loadTriggers(1);
      }
    } catch (error) {
      if (mountedRef.current) setRulesError(getParsedApiError(error));
    } finally {
      finishRuleOperation(rule.id, 'test');
    }
  };

  return (
    <AppPage className="space-y-5">
      <PageHeader
        title={text.title}
        description={text.description}
        actions={(
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setCreateError(null);
              setCreateRuleModalOpen(true);
            }}
          >
            {text.createRule}
          </Button>
        )}
      />

      {createSuccess ? (
        <InlineAlert
          title={text.createSuccess}
          message={createSuccess}
          variant="success"
          action={(
            <Button type="button" variant="ghost" size="md" className="h-auto px-1 text-sm underline" onClick={() => setCreateSuccess(null)}>
              {t('common.close')}
            </Button>
          )}
        />
      ) : null}

      <Modal
        isOpen={createRuleModalOpen}
        onClose={() => {
          if (!createLoading) setCreateRuleModalOpen(false);
        }}
        title={text.createRule}
      >
        {createError ? <ApiErrorAlert error={createError} onDismiss={() => setCreateError(null)} className="mb-4" /> : null}
        <AlertRuleForm
          onSubmit={async (payload) => {
            const ok = await handleCreateRule(payload);
            if (ok) {
              setCreateRuleModalOpen(false);
            }
            return ok;
          }}
          isSubmitting={createLoading}
        />
      </Modal>

      <SegmentedControl
        value={activeView}
        options={[
          { value: 'rules', label: ALERT_LIST_TEXT[language].title },
          { value: 'history', label: ALERT_TRIGGER_TEXT[language].title },
          { value: 'notifications', label: text.notificationAttempts },
        ]}
        onChange={setActiveView}
        ariaLabel={text.title}
        getPanelId={(view) => `alerts-${view}-panel`}
      />

      {activeView === 'rules' ? (
        <section
          id="alerts-rules-panel"
          role="tabpanel"
          aria-label={ALERT_LIST_TEXT[language].title}
          className="flex h-full min-h-0 flex-col gap-4"
        >
          {rulesError ? <ApiErrorAlert error={rulesError} onDismiss={() => setRulesError(null)} /> : null}
          <AlertRuleList
            className="flex flex-col"
            rules={rules}
            total={rulesTotal}
            page={rulesPage}
            pageSize={PAGE_SIZE}
            isLoading={rulesLoading}
            enabledFilter={enabledFilter}
            alertTypeFilter={alertTypeFilter}
            onEnabledFilterChange={(value) => {
              setEnabledFilter(value);
              setRulesPage(1);
            }}
            onAlertTypeFilterChange={(value) => {
              setAlertTypeFilter(value);
              setRulesPage(1);
            }}
            onPageChange={setRulesPage}
            onToggleEnabled={(rule) => void handleToggleEnabled(rule)}
            onDelete={(rule) => void handleDeleteRule(rule)}
            onTest={(rule) => void handleTestRule(rule)}
            busyRules={busyRules}
          />
          {testResult ? (
            <InlineAlert
              title={text.testResult}
              variant={testVariant(testResult.response)}
              message={(
                <div className="space-y-2">
                  <div className="font-medium">{formatUiText(controlsText.testRule, { name: testResult.ruleName })}</div>
                  {renderTestResultMessage(testResult.response, language)}
                </div>
              )}
            />
          ) : null}
        </section>
      ) : null}

      {activeView === 'history' ? (
        <section id="alerts-history-panel" role="tabpanel" aria-label={ALERT_TRIGGER_TEXT[language].title} className="space-y-4">
          {triggersError ? <ApiErrorAlert error={triggersError} onDismiss={() => setTriggersError(null)} /> : null}
          <AlertTriggerHistory
            triggers={triggers}
            isLoading={triggersLoading}
            page={triggersPage}
            pageSize={PAGE_SIZE}
            total={triggersTotal}
            lastUpdated={triggersLastUpdated}
            onPageChange={setTriggersPage}
            onRefresh={() => void loadTriggers(triggersPage)}
          />
        </section>
      ) : null}

      {activeView === 'notifications' ? (
        <section id="alerts-notifications-panel" role="tabpanel" aria-label={text.notificationAttempts} className="space-y-4">
          {notificationsError ? <ApiErrorAlert error={notificationsError} onDismiss={() => setNotificationsError(null)} /> : null}
          <Card title={text.notificationAttempts} subtitle={text.notificationResults} variant="bordered" padding="md">
            <Toolbar
              className="mb-3"
              left={(
                <>
                  <Select
                    label={text.channel}
                    value={notificationChannelFilter}
                    onChange={(value) => {
                      setNotificationChannelFilter(value);
                      setNotificationsPage(1);
                    }}
                    options={[
                      { value: 'all', label: t('usage.period.all') },
                      ...[
                        'wechat',
                        'feishu',
                        'telegram',
                        'dingtalk',
                        'email',
                        'discord',
                        'slack',
                        'pushplus',
                        'pushover',
                        'ntfy',
                        'gotify',
                        'serverchan3',
                        'astrbot',
                        'custom',
                        '__cooldown__',
                        '__cooldown_read_failed__',
                        '__noise_suppressed__',
                        '__no_channel__',
                        '__dispatch__',
                        '__context__',
                      ].map((channel) => ({ value: channel, label: formatNotificationChannel(channel, language) })),
                    ]}
                  />
                  <Select
                    label={text.status}
                    value={notificationSuccessFilter}
                    onChange={(value) => {
                      setNotificationSuccessFilter(value as 'all' | 'success' | 'failure');
                      setNotificationsPage(1);
                    }}
                    options={[
                      { value: 'all', label: t('usage.period.all') },
                      { value: 'success', label: ALERT_NOTIFICATION_STATUS_LABELS[language].success },
                      { value: 'failure', label: ALERT_NOTIFICATION_STATUS_LABELS[language].failure },
                    ]}
                  />
                </>
              )}
              right={(
                <>
                  {notificationsLastUpdated ? (
                    <span className="text-xs text-muted-text">
                      {formatUiText(controlsText.lastUpdated, {
                        time: formatUiDateTime(notificationsLastUpdated, language, { dateStyle: 'medium', timeStyle: 'short' }),
                      })}
                    </span>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => void loadNotifications(notificationsPage)}
                    isLoading={notificationsLoading}
                    loadingText={text.loadingNotifications}
                  >
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    {controlsText.refresh}
                  </Button>
                </>
              )}
            />
            <DataTable
              ariaLabel={text.notificationAttempts}
              columns={notificationColumns}
              rows={notifications}
              getRowKey={(notification) => notification.id}
              isLoading={notificationsLoading}
              loadingLabel={text.loadingNotifications}
              emptyState={(
                <StatePanel status="empty"
                  icon={<BellRing className="h-6 w-6" />}
                  title={text.noNotifications}
                  description={text.noNotificationsDescription}
                />
              )}
              minWidthClassName="min-w-170"
            />
            <Pagination
              currentPage={notificationsPage}
              totalPages={Math.max(1, Math.ceil(notificationsTotal / PAGE_SIZE))}
              onPageChange={setNotificationsPage}
              className="mt-4"
            />
          </Card>
        </section>
      ) : null}
    </AppPage>
  );
};

export default AlertsPage;
