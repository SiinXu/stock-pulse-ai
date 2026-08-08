// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Dual-mode state for AlertsWorkspace:
 * - Standalone (`urlOwned`): URL is the source of truth via alertsUrlSchema.
 * - Embedded: local React state only (Signal Center owns the route).
 */
import { useCallback, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { readParams, writeParams } from '../../utils/urlState';
import type { AlertRuleEnabledFilter, AlertTypeFilter } from './AlertRuleList';
import {
  alertsUrlSchema,
  type AlertsUrlPatch,
  type AlertsUrlView,
  type NotificationSuccessFilter,
} from './alertsUrlState';

export type UseAlertsWorkspaceUrlStateOptions = {
  /** When false (standalone), URL owns filters/tabs/selection. */
  embedded: boolean;
  controlledActiveView?: AlertsUrlView;
  onActiveViewChange?: (view: AlertsUrlView) => void;
  selectedTriggerIdProp?: number | null;
};

export function useAlertsWorkspaceUrlState(options: UseAlertsWorkspaceUrlStateOptions) {
  const {
    embedded,
    controlledActiveView,
    onActiveViewChange,
    selectedTriggerIdProp = null,
  } = options;
  const location = useLocation();
  const navigate = useNavigate();
  const urlOwned = !embedded;

  const urlState = useMemo(
    () => (urlOwned ? readParams(alertsUrlSchema, location.search) : null),
    [location.search, urlOwned],
  );

  const patchUrl = useCallback((patch: AlertsUrlPatch) => {
    if (!urlOwned) return;
    const next = writeParams(alertsUrlSchema, patch, { search: location.search });
    navigate(
      { pathname: location.pathname, search: next.search, hash: location.hash },
      { replace: next.history === 'replace' },
    );
  }, [location.hash, location.pathname, location.search, navigate, urlOwned]);

  const [localView, setLocalView] = useState<AlertsUrlView>('rules');
  const [localEnabledFilter, setLocalEnabledFilter] = useState<AlertRuleEnabledFilter>('all');
  const [localAlertTypeFilter, setLocalAlertTypeFilter] = useState<AlertTypeFilter>('all');
  const [localRulesPage, setLocalRulesPage] = useState(1);
  const [localTriggersPage, setLocalTriggersPage] = useState(1);
  const [localNotificationsPage, setLocalNotificationsPage] = useState(1);
  const [localChannelFilter, setLocalChannelFilter] = useState('all');
  const [localSuccessFilter, setLocalSuccessFilter] = useState<NotificationSuccessFilter>('all');

  const activeView: AlertsUrlView = controlledActiveView
    ?? (urlOwned && urlState ? (urlState.view as AlertsUrlView) : localView);

  const setActiveView = useCallback((view: AlertsUrlView) => {
    if (controlledActiveView === undefined) {
      if (urlOwned) patchUrl({ view });
      else setLocalView(view);
    }
    onActiveViewChange?.(view);
  }, [controlledActiveView, onActiveViewChange, patchUrl, urlOwned]);

  const enabledFilter: AlertRuleEnabledFilter = urlOwned && urlState
    ? (urlState.enabled as AlertRuleEnabledFilter)
    : localEnabledFilter;
  const alertTypeFilter: AlertTypeFilter = urlOwned && urlState
    ? (urlState.type as AlertTypeFilter)
    : localAlertTypeFilter;
  const rulesPage = urlOwned && urlState ? (urlState.page ?? 1) : localRulesPage;
  const triggersPage = urlOwned && urlState ? (urlState.historyPage ?? 1) : localTriggersPage;
  const notificationsPage = urlOwned && urlState
    ? (urlState.notificationsPage ?? 1)
    : localNotificationsPage;
  const notificationChannelFilter = urlOwned && urlState
    ? urlState.channel
    : localChannelFilter;
  const notificationSuccessFilter: NotificationSuccessFilter = urlOwned && urlState
    ? (urlState.success as NotificationSuccessFilter)
    : localSuccessFilter;
  const selectedAlertId = urlOwned && urlState ? urlState.alert : null;
  const selectedTriggerId = selectedTriggerIdProp
    ?? (urlOwned && urlState ? urlState.trigger : null)
    ?? null;

  const setEnabledFilter = useCallback((value: AlertRuleEnabledFilter) => {
    if (urlOwned) {
      patchUrl({ enabled: value, page: 1 });
      return;
    }
    setLocalEnabledFilter(value);
  }, [patchUrl, urlOwned]);

  const setAlertTypeFilter = useCallback((value: AlertTypeFilter) => {
    if (urlOwned) {
      patchUrl({ type: value, page: 1 });
      return;
    }
    setLocalAlertTypeFilter(value);
  }, [patchUrl, urlOwned]);

  const setRulesPage = useCallback((page: number) => {
    if (urlOwned) {
      patchUrl({ page });
      return;
    }
    setLocalRulesPage(page);
  }, [patchUrl, urlOwned]);

  const setTriggersPage = useCallback((page: number) => {
    if (urlOwned) {
      patchUrl({ historyPage: page });
      return;
    }
    setLocalTriggersPage(page);
  }, [patchUrl, urlOwned]);

  const setNotificationsPage = useCallback((page: number) => {
    if (urlOwned) {
      patchUrl({ notificationsPage: page });
      return;
    }
    setLocalNotificationsPage(page);
  }, [patchUrl, urlOwned]);

  const setNotificationChannelFilter = useCallback((value: string) => {
    if (urlOwned) {
      patchUrl({ channel: value, notificationsPage: 1 });
      return;
    }
    setLocalChannelFilter(value);
  }, [patchUrl, urlOwned]);

  const setNotificationSuccessFilter = useCallback((value: NotificationSuccessFilter) => {
    if (urlOwned) {
      patchUrl({ success: value, notificationsPage: 1 });
      return;
    }
    setLocalSuccessFilter(value);
  }, [patchUrl, urlOwned]);

  const setSelectedAlertId = useCallback((alertId: number | null) => {
    if (urlOwned) {
      patchUrl({ alert: alertId });
    }
  }, [patchUrl, urlOwned]);

  return {
    urlOwned,
    patchUrl,
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
