import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { ApiErrorAlert, AppPage, Button, Card, DataTable, type DataTableColumn, InlineAlert, Loading, Modal, PageHeader, Pagination } from '../components/common';
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
  ALERT_PAGE_TEXT,
  ALERT_TRIGGER_TEXT,
} from '../locales/alerts';
import { formatUiDateTime } from '../utils/uiLocale';

const PAGE_SIZE = 20;

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

  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<ParsedApiError | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [editRule, setEditRule] = useState<AlertRuleItem | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editOpening, setEditOpening] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<ParsedApiError | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState<string | null>(null);
  const [busyRules, setBusyRules] = useState<AlertRuleBusyMap>({});
  const [testResult, setTestResult] = useState<{
    ruleId: number;
    ruleName: string;
    response: AlertRuleTestResponse;
  } | null>(null);
  const rulesRequestIdRef = useRef(0);
  const triggersRequestIdRef = useRef(0);
  const notificationsRequestIdRef = useRef(0);
  const editRequestIdRef = useRef(0);
  const busyRulesRef = useRef<Map<number, AlertRuleBusyAction>>(new Map());
  const mountedRef = useRef(true);

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
      const response = await alertsApi.listNotifications({ page, pageSize: PAGE_SIZE });
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
  }, []);

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

  const handleEditOpen = async (rule: AlertRuleItem) => {
    const requestId = editRequestIdRef.current + 1;
    editRequestIdRef.current = requestId;
    setEditError(null);
    setEditRule(null);
    setEditModalOpen(true);
    setEditOpening(true);
    try {
      // Load the current server state so the edit starts from the latest
      // values rather than a possibly stale list row (concurrent-change guard).
      const fresh = await alertsApi.getRule(rule.id);
      // Latest-request-wins: opening edit on B after A must not let A's slower
      // response seed the form with the wrong rule.
      if (!mountedRef.current || editRequestIdRef.current !== requestId) return;
      setEditRule(fresh);
    } catch (error) {
      if (!mountedRef.current || editRequestIdRef.current !== requestId) return;
      setEditError(getParsedApiError(error));
    } finally {
      if (mountedRef.current && editRequestIdRef.current === requestId) setEditOpening(false);
    }
  };

  const handleUpdateRule = async (payload: AlertRuleCreateRequest) => {
    if (!editRule) return false;
    setEditLoading(true);
    setEditError(null);
    setUpdateSuccess(null);
    try {
      const updated = await alertsApi.updateRule(editRule.id, payload);
      if (!mountedRef.current) return false;
      setUpdateSuccess(formatUiText(text.updated, { name: updated.name }));
      await loadRules(rulesPage);
      return true;
    } catch (error) {
      if (mountedRef.current) setEditError(getParsedApiError(error));
      return false;
    } finally {
      if (mountedRef.current) setEditLoading(false);
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

  const notificationColumns: DataTableColumn<AlertNotificationItem>[] = [
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
    },
    {
      id: 'latency',
      header: text.latency,
      cell: (notification) => <>{notification.latencyMs == null ? '--' : `${notification.latencyMs}ms`}</>,
    },
    {
      id: 'time',
      header: text.time,
      cell: (notification) => formatUiDateTime(notification.createdAt, language, { dateStyle: 'medium', timeStyle: 'short' }),
    },
    {
      id: 'diagnostics',
      header: text.diagnostics,
      cell: (notification) => notification.diagnostics ?? '--',
    },
  ];

  return (
    <AppPage className="max-w-none space-y-5">
      <PageHeader
        eyebrow={text.eyebrow}
        title={text.title}
        description={text.description}
        actions={(
          <Button
            type="button"
            variant="primary"
            size="default"
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
            <button type="button" className="min-h-11 min-w-11 text-sm underline" onClick={() => setCreateSuccess(null)}>
              {t('common.close')}
            </button>
          )}
        />
      ) : null}
      {updateSuccess ? (
        <InlineAlert
          title={text.updateSuccess}
          message={updateSuccess}
          variant="success"
          action={(
            <button type="button" className="min-h-11 min-w-11 text-sm underline" onClick={() => setUpdateSuccess(null)}>
              {t('common.close')}
            </button>
          )}
        />
      ) : null}
      {rulesError ? <ApiErrorAlert error={rulesError} onDismiss={() => setRulesError(null)} /> : null}

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

      <Modal
        isOpen={editModalOpen}
        onClose={() => {
          if (!editLoading) {
            setEditModalOpen(false);
            setEditRule(null);
            setEditError(null);
          }
        }}
        title={text.editRule}
      >
        {editError ? <ApiErrorAlert error={editError} onDismiss={() => setEditError(null)} className="mb-4" /> : null}
        {editOpening && !editRule ? (
          <Loading />
        ) : editRule ? (
          <AlertRuleForm
            key={editRule.id}
            mode="edit"
            initialRule={editRule}
            onSubmit={async (payload) => {
              const ok = await handleUpdateRule(payload);
              if (ok) {
                setEditModalOpen(false);
                setEditRule(null);
              }
              return ok;
            }}
            isSubmitting={editLoading}
          />
        ) : null}
      </Modal>

      <div className="flex h-full min-h-0 flex-col gap-4">
          <AlertRuleList
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
            onEdit={(rule) => void handleEditOpen(rule)}
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
        </div>

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

      {notificationsError ? <ApiErrorAlert error={notificationsError} onDismiss={() => setNotificationsError(null)} /> : null}
      <Card title={text.notificationAttempts} subtitle={text.notificationResults} variant="bordered" padding="md">
        <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
          {notificationsLastUpdated ? (
            <span className="text-xs text-muted-text">
              {formatUiText(controlsText.lastUpdated, {
                time: formatUiDateTime(notificationsLastUpdated, language, { dateStyle: 'medium', timeStyle: 'short' }),
              })}
            </span>
          ) : null}
          <Button
            type="button"
            size="default"
            variant="secondary"
            onClick={() => void loadNotifications(notificationsPage)}
            isLoading={notificationsLoading}
            loadingText={text.loadingNotifications}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {controlsText.refresh}
          </Button>
        </div>
        <DataTable<AlertNotificationItem>
          caption={text.notificationAttempts}
          columns={notificationColumns}
          rows={notifications}
          getRowKey={(notification) => notification.id}
          status={notificationsLoading ? { state: 'loading', title: text.loadingNotifications } : undefined}
          emptyState={{
            icon: <BellRing className="h-6 w-6" />,
            title: text.noNotifications,
            description: text.noNotificationsDescription,
          }}
          density="compact"
          minWidth="content"
        />
        <Pagination
          currentPage={notificationsPage}
          totalPages={Math.max(1, Math.ceil(notificationsTotal / PAGE_SIZE))}
          onPageChange={setNotificationsPage}
          className="mt-4"
        />
      </Card>
    </AppPage>
  );
};

export default AlertsPage;
