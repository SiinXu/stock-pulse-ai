// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Router-owned state for AlertsWorkspace. Signal Center owns the outer tab,
 * history subtab, scope, and trigger selection; this hook owns the embedded
 * Alerts filters, pagination, and selected rule without colliding with them.
 */
import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { readParams, resolveHistoryMode, writeParams } from '../../utils/urlState';
import type { AlertRuleEnabledFilter, AlertTypeFilter } from './AlertRuleList';
import {
  alertsUrlSchema,
  type AlertsUrlPatch,
  type AlertsUrlView,
  type NotificationSuccessFilter,
} from './alertsUrlState';

export type UseAlertsWorkspaceUrlStateOptions = {
  controlledActiveView?: AlertsUrlView;
  onActiveViewChange?: (view: AlertsUrlView) => void;
  selectedTriggerIdProp?: number | null;
};

export function useAlertsWorkspaceUrlState(options: UseAlertsWorkspaceUrlStateOptions) {
  const {
    controlledActiveView,
    onActiveViewChange,
    selectedTriggerIdProp = null,
  } = options;
  const [searchParams, setSearchParams] = useSearchParams();
  const serializedSearch = searchParams.toString();
  const urlState = useMemo(
    () => readParams(alertsUrlSchema, serializedSearch),
    [serializedSearch],
  );

  const patchUrl = useCallback((patch: AlertsUrlPatch) => {
    const patchedKeys = Object.keys(patch) as Array<keyof typeof alertsUrlSchema>;
    const history = resolveHistoryMode(alertsUrlSchema, patchedKeys);
    setSearchParams(
      (current) => writeParams(alertsUrlSchema, patch, { search: current }).params,
      { replace: history === 'replace' },
    );
  }, [setSearchParams]);

  const [localView, setLocalView] = useState<AlertsUrlView>('rules');

  const activeView: AlertsUrlView = controlledActiveView
    ?? localView;

  const setActiveView = useCallback((view: AlertsUrlView) => {
    if (controlledActiveView === undefined) {
      setLocalView(view);
    }
    onActiveViewChange?.(view);
  }, [controlledActiveView, onActiveViewChange]);

  const enabledFilter = urlState.enabled as AlertRuleEnabledFilter;
  const alertTypeFilter = urlState.type as AlertTypeFilter;
  const rulesPage = urlState.page ?? 1;
  const triggersPage = urlState.historyPage ?? 1;
  const notificationsPage = urlState.notificationsPage ?? 1;
  const notificationChannelFilter = urlState.channel;
  const notificationSuccessFilter = urlState.success as NotificationSuccessFilter;
  const selectedAlertId = urlState.alert;
  const selectedTriggerId = selectedTriggerIdProp;

  const setEnabledFilter = useCallback((value: AlertRuleEnabledFilter) => {
    patchUrl({ enabled: value, page: 1 });
  }, [patchUrl]);

  const setAlertTypeFilter = useCallback((value: AlertTypeFilter) => {
    patchUrl({ type: value, page: 1 });
  }, [patchUrl]);

  const setRulesPage = useCallback((page: number) => {
    patchUrl({ page });
  }, [patchUrl]);

  const setTriggersPage = useCallback((page: number) => {
    patchUrl({ historyPage: page });
  }, [patchUrl]);

  const setNotificationsPage = useCallback((page: number) => {
    patchUrl({ notificationsPage: page });
  }, [patchUrl]);

  const setNotificationChannelFilter = useCallback((value: string) => {
    patchUrl({ channel: value, notificationsPage: 1 });
  }, [patchUrl]);

  const setNotificationSuccessFilter = useCallback((value: NotificationSuccessFilter) => {
    patchUrl({ success: value, notificationsPage: 1 });
  }, [patchUrl]);

  const setSelectedAlertId = useCallback((alertId: number | null) => {
    patchUrl({ alert: alertId });
  }, [patchUrl]);

  return {
    activeView,
    setActiveView,
    enabledFilter,
    setEnabledFilter,
    alertTypeFilter,
    setAlertTypeFilter,
    rulesPage,
    setRulesPage,
    triggersPage,
    setTriggersPage,
    notificationsPage,
    setNotificationsPage,
    notificationChannelFilter,
    setNotificationChannelFilter,
    notificationSuccessFilter,
    setNotificationSuccessFilter,
    selectedAlertId,
    setSelectedAlertId,
    selectedTriggerId,
  };
}
