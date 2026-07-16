import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BellRing } from 'lucide-react';
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
import { ApiErrorAlert, AppPage, Card, EmptyState, InlineAlert, Loading, Modal, PageHeader } from '../components/common';
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
  ALERT_PAGE_TEXT,
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
  const targetResults = result.targetResults ?? [];
  return (
    <div className="space-y-2">
      <div>
        {result.message}
        {` · ${text.status}: `}
        {result.status}
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
                {item.status}
                {item.recordStatus ? ` / ${item.recordStatus}` : ''}
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
  const [triggersLoading, setTriggersLoading] = useState(false);
  const [triggersError, setTriggersError] = useState<ParsedApiError | null>(null);

  const [notifications, setNotifications] = useState<AlertNotificationItem[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<ParsedApiError | null>(null);

  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<ParsedApiError | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [busyRules, setBusyRules] = useState<AlertRuleBusyMap>({});
  const [testResult, setTestResult] = useState<AlertRuleTestResponse | null>(null);
  const rulesRequestIdRef = useRef(0);
  const triggersRequestIdRef = useRef(0);
  const notificationsRequestIdRef = useRef(0);
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

  const loadTriggers = useCallback(async () => {
    const requestId = triggersRequestIdRef.current + 1;
    triggersRequestIdRef.current = requestId;
    const isLatestRequest = () => triggersRequestIdRef.current === requestId;
    setTriggersLoading(true);
    setTriggersError(null);
    try {
      const response = await alertsApi.listTriggers({ page: 1, pageSize: PAGE_SIZE });
      if (!isLatestRequest()) return;
      setTriggers(response.items);
    } catch (error) {
      if (!isLatestRequest()) return;
      setTriggersError(getParsedApiError(error));
    } finally {
      if (isLatestRequest()) setTriggersLoading(false);
    }
  }, []);

  const loadNotifications = useCallback(async () => {
    const requestId = notificationsRequestIdRef.current + 1;
    notificationsRequestIdRef.current = requestId;
    const isLatestRequest = () => notificationsRequestIdRef.current === requestId;
    setNotificationsLoading(true);
    setNotificationsError(null);
    try {
      const response = await alertsApi.listNotifications({ page: 1, pageSize: PAGE_SIZE });
      if (!isLatestRequest()) return;
      setNotifications(response.items);
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
    void loadTriggers();
    void loadNotifications();
  }, [loadNotifications, loadTriggers, rulesLoaded]);

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
      if (mountedRef.current) setTestResult(result);
    } catch (error) {
      if (mountedRef.current) setRulesError(getParsedApiError(error));
    } finally {
      finishRuleOperation(rule.id, 'test');
    }
  };

  return (
    <AppPage className="max-w-none space-y-5">
      <PageHeader
        eyebrow={text.eyebrow}
        title={text.title}
        description={text.description}
        actions={(
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-2"
            onClick={() => {
              setCreateError(null);
              setCreateRuleModalOpen(true);
            }}
          >
            {text.createRule}
          </button>
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

      <div className="flex h-full min-h-0 flex-col gap-4">
          <AlertRuleList
            className="flex h-full min-h-0 flex-col"
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
              variant={testVariant(testResult)}
              message={renderTestResultMessage(testResult, language)}
            />
          ) : null}
        </div>

      {triggersError ? <ApiErrorAlert error={triggersError} onDismiss={() => setTriggersError(null)} /> : null}
      <AlertTriggerHistory triggers={triggers} isLoading={triggersLoading} />

      {notificationsError ? <ApiErrorAlert error={notificationsError} onDismiss={() => setNotificationsError(null)} /> : null}
      <Card title={text.notificationAttempts} subtitle={text.notificationResults} variant="bordered" padding="md">
        {notificationsLoading ? <Loading label={text.loadingNotifications} /> : null}
        {!notificationsLoading && notifications.length === 0 ? (
          <EmptyState
            icon={<BellRing className="h-6 w-6" />}
            title={text.noNotifications}
            description={text.noNotificationsDescription}
          />
        ) : null}
        {!notificationsLoading && notifications.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead className="border-b border-border/60 text-xs uppercase text-muted-text">
                <tr>
                  <th className="px-3 py-2 font-medium">{text.channel}</th>
                  <th className="px-3 py-2 font-medium">{text.status}</th>
                  <th className="px-3 py-2 font-medium">{text.errorCode}</th>
                  <th className="px-3 py-2 font-medium">{text.latency}</th>
                  <th className="px-3 py-2 font-medium">{text.time}</th>
                  <th className="px-3 py-2 font-medium">{text.diagnostics}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {notifications.map((notification) => (
                  <tr key={notification.id}>
                    <td className="px-3 py-3">{formatNotificationChannel(notification.channel, language)}</td>
                    <td className="px-3 py-3">{formatNotificationStatus(notification, language)}</td>
                    <td className="px-3 py-3">{notification.errorCode ?? '--'}</td>
                    <td className="px-3 py-3">{notification.latencyMs == null ? '--' : `${notification.latencyMs}ms`}</td>
                    <td className="px-3 py-3">{formatUiDateTime(notification.createdAt, language, { dateStyle: 'medium', timeStyle: 'short' })}</td>
                    <td className="px-3 py-3">{notification.diagnostics ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </AppPage>
  );
};

export default AlertsPage;
