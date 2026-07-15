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
import { createRequestKey, useAsyncResource } from '../hooks/useAsyncResource';

const PAGE_SIZE = 20;

interface AlertRulesResourceData {
  items: AlertRuleItem[];
  total: number;
  page: number;
}

const EMPTY_ALERT_RULES: AlertRulesResourceData = { items: [], total: 0, page: 1 };

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
  const [rulesPage, setRulesPage] = useState(1);
  const [enabledFilter, setEnabledFilter] = useState<AlertRuleEnabledFilter>('all');
  const [alertTypeFilter, setAlertTypeFilter] = useState<AlertTypeFilter>('all');
  const rulesQueryRef = useRef({ page: 1, enabledFilter, alertTypeFilter });
  const [rulesResource, rulesRequests] = useAsyncResource<AlertRulesResourceData, ParsedApiError>({
    initialData: EMPTY_ALERT_RULES,
    isEmpty: (data) => data.items.length === 0,
  });
  const [triggersResource, triggersRequests] = useAsyncResource<AlertTriggerItem[], ParsedApiError>({
    initialData: [],
    isEmpty: (items) => items.length === 0,
  });
  const [notificationsResource, notificationsRequests] = useAsyncResource<AlertNotificationItem[], ParsedApiError>({
    initialData: [],
    isEmpty: (items) => items.length === 0,
  });
  const rules = rulesResource.data.items;
  const rulesTotal = rulesResource.data.total;
  const rulesLoading = rulesResource.status === 'idle' || rulesResource.status === 'loading';
  const triggers = triggersResource.data;
  const triggersLoading = triggersResource.status === 'idle' || triggersResource.status === 'loading';
  const notifications = notificationsResource.data;
  const notificationsLoading = notificationsResource.status === 'idle' || notificationsResource.status === 'loading';

  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<ParsedApiError | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [ruleMutationError, setRuleMutationError] = useState<ParsedApiError | null>(null);
  const [busyRules, setBusyRules] = useState<Record<number, AlertRuleBusyAction>>({});
  const [testResult, setTestResult] = useState<AlertRuleTestResponse | null>(null);

  useEffect(() => {
    rulesQueryRef.current = { page: rulesPage, enabledFilter, alertTypeFilter };
  }, [alertTypeFilter, enabledFilter, rulesPage]);

  const loadRules = useCallback(async (
    pageOverride?: number,
    options: { retainData: boolean } = { retainData: false },
  ) => {
    const currentQuery = rulesQueryRef.current;
    const requestedPage = pageOverride ?? currentQuery.page;
    const baseQuery = {
      enabled: enabledFilterToQuery(currentQuery.enabledFilter),
      alertType: alertTypeFilterToQuery(currentQuery.alertTypeFilter),
      pageSize: PAGE_SIZE,
    };
    const makeRequest = (page: number) => rulesRequests.begin(
      createRequestKey('alert-rules', [baseQuery.enabled ?? null, baseQuery.alertType ?? null, page, PAGE_SIZE]),
      { retainData: options.retainData },
    );
    let request = makeRequest(requestedPage);
    try {
      let response = await alertsApi.listRules({ ...baseQuery, page: requestedPage });
      if (!rulesRequests.isCurrent(request)) return null;
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (response.items.length === 0 && response.total > 0 && requestedPage > lastPage) {
        rulesQueryRef.current = { ...rulesQueryRef.current, page: lastPage };
        setRulesPage(lastPage);
        request = makeRequest(lastPage);
        response = await alertsApi.listRules({ ...baseQuery, page: lastPage });
        if (!rulesRequests.isCurrent(request)) return null;
      } else if (pageOverride !== undefined && pageOverride !== currentQuery.page) {
        rulesQueryRef.current = { ...rulesQueryRef.current, page: pageOverride };
        setRulesPage(pageOverride);
      }
      return rulesRequests.resolve(request, {
        items: response.items,
        total: response.total,
        page: response.page,
      }) ? response : null;
    } catch (error) {
      rulesRequests.reject(request, getParsedApiError(error));
      return null;
    }
  }, [rulesRequests]);

  const loadTriggers = useCallback(async () => {
    const request = triggersRequests.begin(
      createRequestKey('alert-triggers', [1, PAGE_SIZE]),
      { retainData: true },
    );
    try {
      const response = await alertsApi.listTriggers({ page: 1, pageSize: PAGE_SIZE });
      triggersRequests.resolve(request, response.items);
    } catch (error) {
      triggersRequests.reject(request, getParsedApiError(error));
    }
  }, [triggersRequests]);

  const loadNotifications = useCallback(async () => {
    const request = notificationsRequests.begin(
      createRequestKey('alert-notifications', [1, PAGE_SIZE]),
      { retainData: true },
    );
    try {
      const response = await alertsApi.listNotifications({ page: 1, pageSize: PAGE_SIZE });
      notificationsRequests.resolve(request, response.items);
    } catch (error) {
      notificationsRequests.reject(request, getParsedApiError(error));
    }
  }, [notificationsRequests]);

  useEffect(() => {
    void loadRules();
  }, [alertTypeFilter, enabledFilter, loadRules, rulesPage]);

  useEffect(() => {
    void loadTriggers();
    void loadNotifications();
  }, [loadNotifications, loadTriggers]);

  const handleCreateRule = async (payload: AlertRuleCreateRequest) => {
    setCreateLoading(true);
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await alertsApi.createRule(payload);
      setCreateSuccess(formatUiText(text.created, { name: created.name }));
      await loadRules(1, { retainData: true });
      return true;
    } catch (error) {
      setCreateError(getParsedApiError(error));
      return false;
    } finally {
      setCreateLoading(false);
    }
  };

  const handleToggleEnabled = async (rule: AlertRuleItem) => {
    const action: AlertRuleBusyAction = 'toggle';
    setBusyRules((current) => ({ ...current, [rule.id]: action }));
    setRuleMutationError(null);
    try {
      if (rule.enabled) {
        await alertsApi.disableRule(rule.id);
      } else {
        await alertsApi.enableRule(rule.id);
      }
      await loadRules(undefined, { retainData: true });
    } catch (error) {
      setRuleMutationError(getParsedApiError(error));
    } finally {
      setBusyRules((current) => {
        if (current[rule.id] !== action) return current;
        const next = { ...current };
        delete next[rule.id];
        return next;
      });
    }
  };

  const handleDeleteRule = async (rule: AlertRuleItem) => {
    const action: AlertRuleBusyAction = 'delete';
    setBusyRules((current) => ({ ...current, [rule.id]: action }));
    setRuleMutationError(null);
    try {
      await alertsApi.deleteRule(rule.id);
      await loadRules(undefined, { retainData: true });
    } catch (error) {
      setRuleMutationError(getParsedApiError(error));
    } finally {
      setBusyRules((current) => {
        if (current[rule.id] !== action) return current;
        const next = { ...current };
        delete next[rule.id];
        return next;
      });
    }
  };

  const handleTestRule = async (rule: AlertRuleItem) => {
    const action: AlertRuleBusyAction = 'test';
    setBusyRules((current) => ({ ...current, [rule.id]: action }));
    setRuleMutationError(null);
    setTestResult(null);
    try {
      const result = await alertsApi.testRule(rule.id);
      setTestResult(result);
    } catch (error) {
      setRuleMutationError(getParsedApiError(error));
    } finally {
      setBusyRules((current) => {
        if (current[rule.id] !== action) return current;
        const next = { ...current };
        delete next[rule.id];
        return next;
      });
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
            <button type="button" className="text-sm underline" onClick={() => setCreateSuccess(null)}>
              {t('common.close')}
            </button>
          )}
        />
      ) : null}
      {rulesResource.error ? (
        <ApiErrorAlert error={rulesResource.error} onDismiss={rulesRequests.clearError} />
      ) : null}
      {ruleMutationError ? (
        <ApiErrorAlert error={ruleMutationError} onDismiss={() => setRuleMutationError(null)} />
      ) : null}

      <Modal isOpen={createRuleModalOpen} onClose={() => setCreateRuleModalOpen(false)} title={text.createRule}>
        {createError ? (
          <ApiErrorAlert error={createError} className="mb-4" onDismiss={() => setCreateError(null)} />
        ) : null}
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
              rulesQueryRef.current = { ...rulesQueryRef.current, enabledFilter: value, page: 1 };
              setEnabledFilter(value);
              setRulesPage(1);
            }}
            onAlertTypeFilterChange={(value) => {
              rulesQueryRef.current = { ...rulesQueryRef.current, alertTypeFilter: value, page: 1 };
              setAlertTypeFilter(value);
              setRulesPage(1);
            }}
            onPageChange={(page) => {
              rulesQueryRef.current = { ...rulesQueryRef.current, page };
              setRulesPage(page);
            }}
            onToggleEnabled={(rule) => void handleToggleEnabled(rule)}
            onDelete={(rule) => void handleDeleteRule(rule)}
            onTest={(rule) => void handleTestRule(rule)}
            busyRules={busyRules}
            showEmptyState={rulesResource.status !== 'error'}
          />
          {testResult ? (
            <InlineAlert
              title={text.testResult}
              variant={testVariant(testResult)}
              message={renderTestResultMessage(testResult, language)}
            />
          ) : null}
        </div>

      {triggersResource.error ? (
        <ApiErrorAlert error={triggersResource.error} onDismiss={triggersRequests.clearError} />
      ) : null}
      <AlertTriggerHistory
        triggers={triggers}
        isLoading={triggersLoading}
        showEmptyState={triggersResource.status !== 'error'}
      />

      {notificationsResource.error ? (
        <ApiErrorAlert error={notificationsResource.error} onDismiss={notificationsRequests.clearError} />
      ) : null}
      <Card title={text.notificationAttempts} subtitle={text.notificationResults} variant="bordered" padding="md">
        {notificationsLoading ? <Loading label={text.loadingNotifications} /> : null}
        {!notificationsLoading && notificationsResource.status !== 'error' && notifications.length === 0 ? (
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
