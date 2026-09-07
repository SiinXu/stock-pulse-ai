// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { AnalysisContextPackOverview, MarketPhaseSummary } from './analysis';
import type { DecisionSignalItem } from './decisionSignals';
import type {
  EventAlertEventContext,
  EventAlertImpactContext,
  EventAlertImpactResult,
} from './eventAlerts';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiRule = components['schemas']['AlertRuleItem'];
type OpenApiCreate = components['schemas']['AlertRuleCreateRequest'];
type OpenApiList = components['schemas']['AlertRuleListResponse'];
type OpenApiDelete = components['schemas']['AlertDeleteResponse'];
type OpenApiTest = components['schemas']['AlertRuleTestResponse'];
type OpenApiTargetResult = components['schemas']['AlertRuleTargetResult'];
type OpenApiTrigger = components['schemas']['AlertTriggerItem'];
type OpenApiTriggerList = components['schemas']['AlertTriggerListResponse'];
type OpenApiNotification = components['schemas']['AlertNotificationItem'];
type OpenApiNotificationList = components['schemas']['AlertNotificationListResponse'];
type OpenApiUpdate = components['schemas']['AlertRuleUpdateRequest'];

type OpenApiListOp = operations['list_rules_api_v1_alerts_rules_get'];
type OpenApiCreateOp = operations['create_rule_api_v1_alerts_rules_post'];
type OpenApiGetOp = operations['get_rule_api_v1_alerts_rules__rule_id__get'];
type OpenApiUpdateOp = operations['update_rule_api_v1_alerts_rules__rule_id__patch'];
type OpenApiDeleteOp = operations['delete_rule_api_v1_alerts_rules__rule_id__delete'];
type OpenApiEnableOp = operations['enable_rule_api_v1_alerts_rules__rule_id__enable_post'];
type OpenApiDisableOp = operations['disable_rule_api_v1_alerts_rules__rule_id__disable_post'];
type OpenApiTestOp = operations['test_rule_api_v1_alerts_rules__rule_id__test_post'];
type OpenApiTriggerListOp = operations['list_triggers_api_v1_alerts_triggers_get'];
type OpenApiNotificationListOp = operations['list_notifications_api_v1_alerts_notifications_get'];

type OpenApiListPathGet = paths['/api/v1/alerts/rules']['get'];
type OpenApiCreatePathPost = paths['/api/v1/alerts/rules']['post'];
type OpenApiGetPathGet = paths['/api/v1/alerts/rules/{rule_id}']['get'];
type OpenApiUpdatePathPatch = paths['/api/v1/alerts/rules/{rule_id}']['patch'];
type OpenApiDeletePathDelete = paths['/api/v1/alerts/rules/{rule_id}']['delete'];
type OpenApiEnablePathPost = paths['/api/v1/alerts/rules/{rule_id}/enable']['post'];
type OpenApiDisablePathPost = paths['/api/v1/alerts/rules/{rule_id}/disable']['post'];
type OpenApiTestPathPost = paths['/api/v1/alerts/rules/{rule_id}/test']['post'];
type OpenApiTriggerListPathGet = paths['/api/v1/alerts/triggers']['get'];
type OpenApiNotificationListPathGet = paths['/api/v1/alerts/notifications']['get'];

type OpenApiListGet200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiCreatePost200 = OpenApiCreateOp['responses']['200']['content']['application/json'];
type OpenApiCreateBody = OpenApiCreateOp['requestBody']['content']['application/json'];
type OpenApiGetGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiUpdatePatch200 = OpenApiUpdateOp['responses']['200']['content']['application/json'];
type OpenApiUpdateBody = OpenApiUpdateOp['requestBody']['content']['application/json'];
type OpenApiDeleteDelete200 = OpenApiDeleteOp['responses']['200']['content']['application/json'];
type OpenApiEnablePost200 = OpenApiEnableOp['responses']['200']['content']['application/json'];
type OpenApiDisablePost200 = OpenApiDisableOp['responses']['200']['content']['application/json'];
type OpenApiTestPost200 = OpenApiTestOp['responses']['200']['content']['application/json'];
type OpenApiTriggerListGet200 = OpenApiTriggerListOp['responses']['200']['content']['application/json'];
type OpenApiNotificationListGet200 = OpenApiNotificationListOp['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiList ? true : false>;
type _ListIsList200 = _Assert<OpenApiList extends OpenApiListGet200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _ListHas200 = _Assert<200 extends keyof OpenApiListOp['responses'] ? true : false>;
type _ListLacks201 = _Assert<201 extends keyof OpenApiListOp['responses'] ? false : true>;
type _Create200IsRule = _Assert<OpenApiCreatePost200 extends OpenApiRule ? true : false>;
type _RuleIsCreate200 = _Assert<OpenApiRule extends OpenApiCreatePost200 ? true : false>;
type _CreateOpIsPath = _Assert<OpenApiCreateOp extends OpenApiCreatePathPost ? true : false>;
type _PathIsCreateOp = _Assert<OpenApiCreatePathPost extends OpenApiCreateOp ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreate ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreate extends OpenApiCreateBody ? true : false>;
type _CreateHas200 = _Assert<200 extends keyof OpenApiCreateOp['responses'] ? true : false>;
type _CreateLacks201 = _Assert<201 extends keyof OpenApiCreateOp['responses'] ? false : true>;
type _Get200IsRule = _Assert<OpenApiGetGet200 extends OpenApiRule ? true : false>;
type _RuleIsGet200 = _Assert<OpenApiRule extends OpenApiGetGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiGetPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiGetPathGet extends OpenApiGetOp ? true : false>;
type _GetNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _GetHas200 = _Assert<200 extends keyof OpenApiGetOp['responses'] ? true : false>;
type _GetLacks201 = _Assert<201 extends keyof OpenApiGetOp['responses'] ? false : true>;
type _Update200IsRule = _Assert<OpenApiUpdatePatch200 extends OpenApiRule ? true : false>;
type _RuleIsUpdate200 = _Assert<OpenApiRule extends OpenApiUpdatePatch200 ? true : false>;
type _UpdateOpIsPath = _Assert<OpenApiUpdateOp extends OpenApiUpdatePathPatch ? true : false>;
type _PathIsUpdateOp = _Assert<OpenApiUpdatePathPatch extends OpenApiUpdateOp ? true : false>;
type _UpdateBodyIsUpdate = _Assert<OpenApiUpdateBody extends OpenApiUpdate ? true : false>;
type _UpdateIsUpdateBody = _Assert<OpenApiUpdate extends OpenApiUpdateBody ? true : false>;
type _UpdateHas200 = _Assert<200 extends keyof OpenApiUpdateOp['responses'] ? true : false>;
type _UpdateLacks201 = _Assert<201 extends keyof OpenApiUpdateOp['responses'] ? false : true>;
type _Delete200IsDelete = _Assert<OpenApiDeleteDelete200 extends OpenApiDelete ? true : false>;
type _DeleteIsDelete200 = _Assert<OpenApiDelete extends OpenApiDeleteDelete200 ? true : false>;
type _DeleteOpIsPath = _Assert<OpenApiDeleteOp extends OpenApiDeletePathDelete ? true : false>;
type _PathIsDeleteOp = _Assert<OpenApiDeletePathDelete extends OpenApiDeleteOp ? true : false>;
type _DeleteNeverRequestBody = _Assert<OpenApiDeleteOp extends { requestBody?: never } ? true : false>;
type _DeleteHas200 = _Assert<200 extends keyof OpenApiDeleteOp['responses'] ? true : false>;
type _DeleteLacks201 = _Assert<201 extends keyof OpenApiDeleteOp['responses'] ? false : true>;
type _Enable200IsRule = _Assert<OpenApiEnablePost200 extends OpenApiRule ? true : false>;
type _RuleIsEnable200 = _Assert<OpenApiRule extends OpenApiEnablePost200 ? true : false>;
type _EnableOpIsPath = _Assert<OpenApiEnableOp extends OpenApiEnablePathPost ? true : false>;
type _PathIsEnableOp = _Assert<OpenApiEnablePathPost extends OpenApiEnableOp ? true : false>;
type _EnableNeverRequestBody = _Assert<OpenApiEnableOp extends { requestBody?: never } ? true : false>;
type _EnableHas200 = _Assert<200 extends keyof OpenApiEnableOp['responses'] ? true : false>;
type _EnableLacks201 = _Assert<201 extends keyof OpenApiEnableOp['responses'] ? false : true>;
type _Disable200IsRule = _Assert<OpenApiDisablePost200 extends OpenApiRule ? true : false>;
type _RuleIsDisable200 = _Assert<OpenApiRule extends OpenApiDisablePost200 ? true : false>;
type _DisableOpIsPath = _Assert<OpenApiDisableOp extends OpenApiDisablePathPost ? true : false>;
type _PathIsDisableOp = _Assert<OpenApiDisablePathPost extends OpenApiDisableOp ? true : false>;
type _DisableNeverRequestBody = _Assert<OpenApiDisableOp extends { requestBody?: never } ? true : false>;
type _DisableHas200 = _Assert<200 extends keyof OpenApiDisableOp['responses'] ? true : false>;
type _DisableLacks201 = _Assert<201 extends keyof OpenApiDisableOp['responses'] ? false : true>;
type _Test200IsTest = _Assert<OpenApiTestPost200 extends OpenApiTest ? true : false>;
type _TestIsTest200 = _Assert<OpenApiTest extends OpenApiTestPost200 ? true : false>;
type _TestOpIsPath = _Assert<OpenApiTestOp extends OpenApiTestPathPost ? true : false>;
type _PathIsTestOp = _Assert<OpenApiTestPathPost extends OpenApiTestOp ? true : false>;
type _TestNeverRequestBody = _Assert<OpenApiTestOp extends { requestBody?: never } ? true : false>;
type _TestHas200 = _Assert<200 extends keyof OpenApiTestOp['responses'] ? true : false>;
type _TestLacks201 = _Assert<201 extends keyof OpenApiTestOp['responses'] ? false : true>;
type _TriggerList200IsTriggerList = _Assert<OpenApiTriggerListGet200 extends OpenApiTriggerList ? true : false>;
type _TriggerListIsTriggerList200 = _Assert<OpenApiTriggerList extends OpenApiTriggerListGet200 ? true : false>;
type _TriggerListOpIsPath = _Assert<OpenApiTriggerListOp extends OpenApiTriggerListPathGet ? true : false>;
type _PathIsTriggerListOp = _Assert<OpenApiTriggerListPathGet extends OpenApiTriggerListOp ? true : false>;
type _TriggerListGetNeverRequestBody = _Assert<OpenApiTriggerListOp extends { requestBody?: never } ? true : false>;
type _TriggerListHas200 = _Assert<200 extends keyof OpenApiTriggerListOp['responses'] ? true : false>;
type _TriggerListLacks201 = _Assert<201 extends keyof OpenApiTriggerListOp['responses'] ? false : true>;
type _NotificationList200IsNotificationList = _Assert<
  OpenApiNotificationListGet200 extends OpenApiNotificationList ? true : false
>;
type _NotificationListIsNotificationList200 = _Assert<
  OpenApiNotificationList extends OpenApiNotificationListGet200 ? true : false
>;
type _NotificationListOpIsPath = _Assert<
  OpenApiNotificationListOp extends OpenApiNotificationListPathGet ? true : false
>;
type _PathIsNotificationListOp = _Assert<
  OpenApiNotificationListPathGet extends OpenApiNotificationListOp ? true : false
>;
type _NotificationListGetNeverRequestBody = _Assert<
  OpenApiNotificationListOp extends { requestBody?: never } ? true : false
>;
type _NotificationListHas200 = _Assert<200 extends keyof OpenApiNotificationListOp['responses'] ? true : false>;
type _NotificationListLacks201 = _Assert<201 extends keyof OpenApiNotificationListOp['responses'] ? false : true>;

type _OpenApiAnchors = [
  _List200IsList,
  _ListIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _ListGetNeverRequestBody,
  _ListHas200,
  _ListLacks201,
  _Create200IsRule,
  _RuleIsCreate200,
  _CreateOpIsPath,
  _PathIsCreateOp,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _CreateHas200,
  _CreateLacks201,
  _Get200IsRule,
  _RuleIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetNeverRequestBody,
  _GetHas200,
  _GetLacks201,
  _Update200IsRule,
  _RuleIsUpdate200,
  _UpdateOpIsPath,
  _PathIsUpdateOp,
  _UpdateBodyIsUpdate,
  _UpdateIsUpdateBody,
  _UpdateHas200,
  _UpdateLacks201,
  _Delete200IsDelete,
  _DeleteIsDelete200,
  _DeleteOpIsPath,
  _PathIsDeleteOp,
  _DeleteNeverRequestBody,
  _DeleteHas200,
  _DeleteLacks201,
  _Enable200IsRule,
  _RuleIsEnable200,
  _EnableOpIsPath,
  _PathIsEnableOp,
  _EnableNeverRequestBody,
  _EnableHas200,
  _EnableLacks201,
  _Disable200IsRule,
  _RuleIsDisable200,
  _DisableOpIsPath,
  _PathIsDisableOp,
  _DisableNeverRequestBody,
  _DisableHas200,
  _DisableLacks201,
  _Test200IsTest,
  _TestIsTest200,
  _TestOpIsPath,
  _PathIsTestOp,
  _TestNeverRequestBody,
  _TestHas200,
  _TestLacks201,
  _TriggerList200IsTriggerList,
  _TriggerListIsTriggerList200,
  _TriggerListOpIsPath,
  _PathIsTriggerListOp,
  _TriggerListGetNeverRequestBody,
  _TriggerListHas200,
  _TriggerListLacks201,
  _NotificationList200IsNotificationList,
  _NotificationListIsNotificationList200,
  _NotificationListOpIsPath,
  _PathIsNotificationListOp,
  _NotificationListGetNeverRequestBody,
  _NotificationListHas200,
  _NotificationListLacks201,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type AlertType =
  | 'price_cross'
  | 'price_change_percent'
  | 'volume_spike'
  | 'ma_price_cross'
  | 'rsi_threshold'
  | 'macd_cross'
  | 'kdj_cross'
  | 'cci_threshold'
  | 'corporate_event'
  | 'portfolio_stop_loss'
  | 'portfolio_concentration'
  | 'portfolio_drawdown'
  | 'portfolio_price_stale'
  | 'market_light_status'
  | 'market_light_score_drop';
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertTargetScope = 'single_symbol' | 'watchlist' | 'portfolio_holdings' | 'portfolio_account' | 'market';
export type AlertDirection = 'above' | 'below' | 'up' | 'down' | 'bullish_cross' | 'bearish_cross';
export type PortfolioStopLossMode = 'near' | 'breach';
export type MarketRegion = 'cn' | 'hk' | 'us';
export type MarketLightStatus = 'yellow' | 'red';
export type AlertDryRunStatus = 'triggered' | 'not_triggered' | 'evaluation_error';
export type AlertTriggerStatus = 'triggered' | 'skipped' | 'degraded' | 'failed';

export type AlertCooldownPolicy = Record<string, unknown> & {
  cooldown_seconds?: unknown;
};

export interface AlertRuleParameters {
  direction?: AlertDirection;
  price?: number;
  changePct?: number;
  multiplier?: number;
  window?: number;
  period?: number;
  threshold?: number;
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  kPeriod?: number;
  dPeriod?: number;
  mode?: PortfolioStopLossMode;
  statuses?: MarketLightStatus[];
  minDrop?: number;
  eventCategories?: string[];
  lookbackHours?: number;
  minItems?: number;
}

export type AlertRuleItem = Override<CamelizeKeys<OpenApiRule>, {
  alertType: AlertType;
  targetScope: AlertTargetScope;
  parameters: AlertRuleParameters;
  severity: AlertSeverity;
  cooldownPolicy?: AlertCooldownPolicy | null;
  notificationPolicy?: Record<string, unknown> | null;
  lastTriggeredAt?: string | null;
  cooldownUntil?: string | null;
  cooldownActive?: boolean | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}>;

export type AlertRuleListResponse = Override<CamelizeKeys<OpenApiList>, {
  items: AlertRuleItem[];
}>;

export type AlertRuleCreateRequest = Override<CamelizeKeys<OpenApiCreate>, {
  name?: string;
  targetScope?: AlertTargetScope;
  enabled?: boolean;
  alertType: AlertType;
  parameters: AlertRuleParameters;
  severity: AlertSeverity;
  cooldownPolicy?: AlertCooldownPolicy | null;
  notificationPolicy?: Record<string, unknown> | null;
}>;

export type AlertDeleteResponse = _BindOpenApiAnchors<CamelizeKeys<OpenApiDelete>>;

export type AlertRuleTargetResult = Override<CamelizeKeys<OpenApiTargetResult>, {
  displayTarget?: string | null;
  recordStatus?: AlertTriggerStatus | null;
}>;

export type AlertRuleTestResponse = Override<CamelizeKeys<OpenApiTest>, {
  targetScope?: AlertTargetScope | string | null;
  status: AlertDryRunStatus;
  observedValue?: unknown;
  degradedCount?: number;
  evaluatedCount?: number;
  skippedCount?: number;
  triggeredCount?: number;
  targetResults?: AlertRuleTargetResult[];
}>;

export type AlertTriggerItem = Override<CamelizeKeys<OpenApiTrigger>, {
  status: AlertTriggerStatus | string;
  alertType?: string | null;
  severity?: AlertSeverity | null;
  marketPhaseSummary?: MarketPhaseSummary | null;
  analysisContextPackOverview?: AnalysisContextPackOverview | null;
  decisionSignalSummary?: Partial<DecisionSignalItem> | null;
  impactContext?: EventAlertImpactContext | null;
  eventContext?: EventAlertEventContext | null;
  impactResult?: EventAlertImpactResult | null;
  suggestedAction?: {
    actionCode?: string | null;
    label?: string | null;
    rationale?: string | null;
    deepLinks?: Record<string, string> | null;
    relevance?: string[] | null;
    autoAnalysis?: {
      status?: string | null;
      submitted?: boolean | null;
      stockCode?: string | null;
      pipeline?: string | null;
      reason?: string | null;
    } | null;
  } | null;
  autoAnalysis?: {
    status?: string | null;
    submitted?: boolean | null;
    stockCode?: string | null;
    pipeline?: string | null;
    reason?: string | null;
  } | null;
}>;

export type AlertTriggerListResponse = Override<CamelizeKeys<OpenApiTriggerList>, {
  items: AlertTriggerItem[];
}>;

export type AlertNotificationItem = CamelizeKeys<OpenApiNotification>;

export type AlertNotificationListResponse = Override<CamelizeKeys<OpenApiNotificationList>, {
  items: AlertNotificationItem[];
}>;

export interface AlertRuleListQuery {
  enabled?: boolean;
  alertType?: AlertType;
  targetScope?: AlertTargetScope;
  target?: string;
  source?: string;
  page?: number;
  pageSize?: number;
}

export interface AlertTriggerListQuery {
  ruleId?: number;
  target?: string;
  status?: string;
  alertType?: 'corporate_event';
  cursor?: string;
  page?: number;
  pageSize?: number;
}

export interface AlertNotificationListQuery {
  triggerId?: number;
  channel?: string;
  success?: boolean;
  page?: number;
  pageSize?: number;
}
