// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Alerts from '../alerts';
import type {
  AlertCooldownPolicy,
  AlertDeleteResponse,
  AlertNotificationItem,
  AlertNotificationListResponse,
  AlertRuleCreateRequest,
  AlertRuleItem,
  AlertRuleListResponse,
  AlertRuleParameters,
  AlertRuleTestResponse,
  AlertTriggerItem,
  AlertTriggerListResponse,
} from '../alerts';

type OpenApiRule = components['schemas']['AlertRuleItem'];
type OpenApiCreate = components['schemas']['AlertRuleCreateRequest'];
type OpenApiList = components['schemas']['AlertRuleListResponse'];
type OpenApiDelete = components['schemas']['AlertDeleteResponse'];
type OpenApiTest = components['schemas']['AlertRuleTestResponse'];
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

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _TenComponents = _Assert<
  (
    | 'AlertRuleItem'
    | 'AlertRuleCreateRequest'
    | 'AlertRuleListResponse'
    | 'AlertDeleteResponse'
    | 'AlertRuleTestResponse'
    | 'AlertRuleTargetResult'
    | 'AlertTriggerItem'
    | 'AlertTriggerListResponse'
    | 'AlertNotificationItem'
    | 'AlertNotificationListResponse'
  ) extends keyof components['schemas'] ? true : false
>;

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

type _PublicRuleNotPath200 = _Assert<AlertRuleItem extends OpenApiCreatePost200 ? false : true>;
type _Path200NotPublicRule = _Assert<OpenApiCreatePost200 extends AlertRuleItem ? false : true>;
type _PublicListNotPath200 = _Assert<AlertRuleListResponse extends OpenApiListGet200 ? false : true>;
type _Path200NotPublicList = _Assert<OpenApiListGet200 extends AlertRuleListResponse ? false : true>;
type _PublicCreateNotBody = _Assert<AlertRuleCreateRequest extends OpenApiCreateBody ? false : true>;
type _BodyNotPublicCreate = _Assert<OpenApiCreateBody extends AlertRuleCreateRequest ? false : true>;
type _PublicTestNotPath200 = _Assert<AlertRuleTestResponse extends OpenApiTestPost200 ? false : true>;
type _Path200NotPublicTest = _Assert<OpenApiTestPost200 extends AlertRuleTestResponse ? false : true>;
type NaiveNotification = CamelizeKeys<OpenApiNotification>;
type _PublicTriggerListNotPath200 = _Assert<AlertTriggerListResponse extends OpenApiTriggerListGet200 ? false : true>;
type _Path200NotPublicTriggerList = _Assert<OpenApiTriggerListGet200 extends AlertTriggerListResponse ? false : true>;
type _PublicNotificationListNotPath200 = _Assert<
  AlertNotificationListResponse extends OpenApiNotificationListGet200 ? false : true
>;
type _Path200NotPublicNotificationList = _Assert<
  OpenApiNotificationListGet200 extends AlertNotificationListResponse ? false : true
>;
type _PublicDeleteIsPath200 = _Assert<AlertDeleteResponse extends OpenApiDeleteDelete200 ? true : false>;
type _Path200IsPublicDelete = _Assert<OpenApiDeleteDelete200 extends AlertDeleteResponse ? true : false>;
type _PublicNotificationIsCamel = _Assert<AlertNotificationItem extends NaiveNotification ? true : false>;
type _CamelIsPublicNotification = _Assert<NaiveNotification extends AlertNotificationItem ? true : false>;
type _UiTriggerHasAlertType = _Assert<'alertType' extends keyof AlertTriggerItem ? true : false>;
type _UiTriggerLacksAlertTypeSnake = _Assert<'alert_type' extends keyof AlertTriggerItem ? false : true>;
type _GeneratedTriggerHasAlertTypeSnake = _Assert<'alert_type' extends keyof OpenApiTrigger ? true : false>;
type _GeneratedTriggerLacksAlertTypeCamel = _Assert<'alertType' extends keyof OpenApiTrigger ? false : true>;
type _UiNotificationHasCreatedAt = _Assert<'createdAt' extends keyof AlertNotificationItem ? true : false>;
type _UiNotificationLacksCreatedAtSnake = _Assert<'created_at' extends keyof AlertNotificationItem ? false : true>;
type _GeneratedNotificationHasCreatedAtSnake = _Assert<'created_at' extends keyof OpenApiNotification ? true : false>;
type _GeneratedNotificationLacksCreatedAtCamel = _Assert<
  'createdAt' extends keyof OpenApiNotification ? false : true
>;

type _UiHasAlertType = _Assert<'alertType' extends keyof AlertRuleItem ? true : false>;
type _UiHasTargetScope = _Assert<'targetScope' extends keyof AlertRuleItem ? true : false>;
type _UiHasPageSize = _Assert<'pageSize' extends keyof AlertRuleListResponse ? true : false>;
type _UiHasCooldownUntil = _Assert<'cooldownUntil' extends keyof AlertRuleItem ? true : false>;
type _UiLacksAlertTypeSnake = _Assert<'alert_type' extends keyof AlertRuleItem ? false : true>;
type _UiLacksTargetScopeSnake = _Assert<'target_scope' extends keyof AlertRuleItem ? false : true>;
type _UiLacksPageSizeSnake = _Assert<'page_size' extends keyof AlertRuleListResponse ? false : true>;
type _UiLacksCooldownUntilSnake = _Assert<'cooldown_until' extends keyof AlertRuleItem ? false : true>;
type _GeneratedHasAlertTypeSnake = _Assert<'alert_type' extends keyof OpenApiRule ? true : false>;
type _GeneratedHasTargetScopeSnake = _Assert<'target_scope' extends keyof OpenApiRule ? true : false>;
type _GeneratedHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiList ? true : false>;
type _GeneratedHasCooldownUntilSnake = _Assert<'cooldown_until' extends keyof OpenApiRule ? true : false>;
type _GeneratedLacksAlertTypeCamel = _Assert<'alertType' extends keyof OpenApiRule ? false : true>;
type _GeneratedLacksTargetScopeCamel = _Assert<'targetScope' extends keyof OpenApiRule ? false : true>;
type _GeneratedLacksPageSizeCamel = _Assert<'pageSize' extends keyof OpenApiList ? false : true>;
type _GeneratedLacksCooldownUntilCamel = _Assert<'cooldownUntil' extends keyof OpenApiRule ? false : true>;

type _UiItemsRequired = _Assert<IsOptional<AlertRuleListResponse, 'items'> extends false ? true : false>;
type _UiTriggerItemsRequired = _Assert<IsOptional<AlertTriggerListResponse, 'items'> extends false ? true : false>;
type _UiNotificationItemsRequired = _Assert<
  IsOptional<AlertNotificationListResponse, 'items'> extends false ? true : false
>;
type _NaiveItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiList>, 'items'>>;
type _NaiveTriggerItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiTriggerList>, 'items'>>;
type _NaiveNotificationItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiNotificationList>, 'items'>>;
type _UiEnabledOptional = _Assert<IsOptional<AlertRuleCreateRequest, 'enabled'>>;
type _UiTargetScopeOptional = _Assert<IsOptional<AlertRuleCreateRequest, 'targetScope'>>;
type _NaiveEnabledRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiCreate>, 'enabled'> extends false ? true : false
>;
type _NaiveTargetScopeRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiCreate>, 'targetScope'> extends false ? true : false
>;
type _UiDegradedOptional = _Assert<IsOptional<AlertRuleTestResponse, 'degradedCount'>>;
type _UiEvaluatedOptional = _Assert<IsOptional<AlertRuleTestResponse, 'evaluatedCount'>>;
type _UiSkippedOptional = _Assert<IsOptional<AlertRuleTestResponse, 'skippedCount'>>;
type _UiTriggeredOptional = _Assert<IsOptional<AlertRuleTestResponse, 'triggeredCount'>>;
type _NaiveDegradedRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiTest>, 'degradedCount'> extends false ? true : false
>;
type _NaiveEvaluatedRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiTest>, 'evaluatedCount'> extends false ? true : false
>;
type _NaiveSkippedRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiTest>, 'skippedCount'> extends false ? true : false
>;
type _NaiveTriggeredRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiTest>, 'triggeredCount'> extends false ? true : false
>;
type _UiSourceRequired = _Assert<IsOptional<AlertRuleItem, 'source'> extends false ? true : false>;

type _CompileTimePins = [
  _TenComponents,
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
  _PublicRuleNotPath200,
  _Path200NotPublicRule,
  _PublicListNotPath200,
  _Path200NotPublicList,
  _PublicCreateNotBody,
  _BodyNotPublicCreate,
  _PublicTestNotPath200,
  _Path200NotPublicTest,
  _PublicTriggerListNotPath200,
  _Path200NotPublicTriggerList,
  _PublicNotificationListNotPath200,
  _Path200NotPublicNotificationList,
  _PublicDeleteIsPath200,
  _Path200IsPublicDelete,
  _PublicNotificationIsCamel,
  _CamelIsPublicNotification,
  _UiTriggerHasAlertType,
  _UiTriggerLacksAlertTypeSnake,
  _GeneratedTriggerHasAlertTypeSnake,
  _GeneratedTriggerLacksAlertTypeCamel,
  _UiNotificationHasCreatedAt,
  _UiNotificationLacksCreatedAtSnake,
  _GeneratedNotificationHasCreatedAtSnake,
  _GeneratedNotificationLacksCreatedAtCamel,
  _UiHasAlertType,
  _UiHasTargetScope,
  _UiHasPageSize,
  _UiHasCooldownUntil,
  _UiLacksAlertTypeSnake,
  _UiLacksTargetScopeSnake,
  _UiLacksPageSizeSnake,
  _UiLacksCooldownUntilSnake,
  _GeneratedHasAlertTypeSnake,
  _GeneratedHasTargetScopeSnake,
  _GeneratedHasPageSizeSnake,
  _GeneratedHasCooldownUntilSnake,
  _GeneratedLacksAlertTypeCamel,
  _GeneratedLacksTargetScopeCamel,
  _GeneratedLacksPageSizeCamel,
  _GeneratedLacksCooldownUntilCamel,
  _UiItemsRequired,
  _UiTriggerItemsRequired,
  _UiNotificationItemsRequired,
  _NaiveItemsOptional,
  _NaiveTriggerItemsOptional,
  _NaiveNotificationItemsOptional,
  _UiEnabledOptional,
  _UiTargetScopeOptional,
  _NaiveEnabledRequired,
  _NaiveTargetScopeRequired,
  _UiDegradedOptional,
  _UiEvaluatedOptional,
  _UiSkippedOptional,
  _UiTriggeredOptional,
  _NaiveDegradedRequired,
  _NaiveEvaluatedRequired,
  _NaiveSkippedRequired,
  _NaiveTriggeredRequired,
  _UiSourceRequired,
];

const ruleBase = {
  id: 7,
  name: 'r',
  targetScope: 'single_symbol' as const,
  target: '600519',
  alertType: 'price_cross' as const,
  parameters: { direction: 'above' as const, price: 1800 },
  severity: 'warning' as const,
  enabled: true,
  source: 'api',
};

const createBase = {
  target: '600519',
  alertType: 'price_cross' as const,
  parameters: { direction: 'above' as const, price: 1800 },
  severity: 'warning' as const,
};

const listMissingItems = {
  total: 0,
  page: 1,
  pageSize: 20,
};

const testMissingCounts = {
  ruleId: 7,
  status: 'not_triggered' as const,
  triggered: false,
  message: 'ok',
};

const uiRule: AlertRuleItem = ruleBase;
void uiRule;
const uiCreate: AlertRuleCreateRequest = createBase;
void uiCreate;
const uiParams: AlertRuleParameters = { direction: 'above', price: 1800 };
void uiParams;
const uiTest: AlertRuleTestResponse = testMissingCounts;
void uiTest;
const uiDelete: AlertDeleteResponse = { deleted: 1 };
void uiDelete;

const uiNotification: AlertNotificationItem = {
  id: 1,
  channel: 'email',
  attempt: 1,
  success: false,
  retryable: true,
};
void uiNotification;

const naiveCreate: CamelizeKeys<OpenApiCreate> = {
  ...createBase,
  enabled: true,
  targetScope: 'single_symbol',
};
void naiveCreate;
// @ts-expect-error naive create requires generated-default enabled and targetScope
const naiveCreateMissing: CamelizeKeys<OpenApiCreate> = createBase;
void naiveCreateMissing;

const naiveListMissing: CamelizeKeys<OpenApiList> = listMissingItems;
void naiveListMissing;
// @ts-expect-error public list items is required
const publicListMissing: AlertRuleListResponse = listMissingItems;
void publicListMissing;

const naiveTriggerListMissing: CamelizeKeys<OpenApiTriggerList> = listMissingItems;
void naiveTriggerListMissing;
// @ts-expect-error public trigger list items is required
const publicTriggerListMissing: AlertTriggerListResponse = listMissingItems;
void publicTriggerListMissing;

const naiveNotificationListMissing: CamelizeKeys<OpenApiNotificationList> = listMissingItems;
void naiveNotificationListMissing;
// @ts-expect-error public notification list items is required
const publicNotificationListMissing: AlertNotificationListResponse = listMissingItems;
void publicNotificationListMissing;

const naiveTestMissing: CamelizeKeys<OpenApiTest> = {
  ...testMissingCounts,
  degradedCount: 0,
  evaluatedCount: 0,
  skippedCount: 0,
  triggeredCount: 0,
};
void naiveTestMissing;
// @ts-expect-error naive test requires degradedCount / evaluatedCount / skippedCount / triggeredCount
const naiveTest: CamelizeKeys<OpenApiTest> = testMissingCounts;
void naiveTest;

const naiveParamsExtra: CamelizeKeys<OpenApiRule>['parameters'] = {
  direction: 'above',
  price: 1800,
  futureParamFlag: true,
};
void naiveParamsExtra;
// @ts-expect-error futureParamFlag is not a public parameters field
const extraParams: AlertRuleParameters = { direction: 'above', price: 1800, futureParamFlag: true };

// @ts-expect-error futureRuleFlag is not a public rule field
const extraRule: AlertRuleItem = { ...ruleBase, futureRuleFlag: true };

// @ts-expect-error futureCreateFlag is not a public create field
const extraCreate: AlertRuleCreateRequest = { ...createBase, futureCreateFlag: true };

const cooldownWithExtra: AlertCooldownPolicy = {
  cooldown_seconds: 3600,
  futureCooldownFlag: true,
};
void cooldownWithExtra;

const naiveBadType: CamelizeKeys<OpenApiRule> = { ...ruleBase, alertType: 'not-a-type' };
void naiveBadType;
// @ts-expect-error not-a-type is not a public AlertType
const publicBadType: AlertRuleItem = { ...ruleBase, alertType: 'not-a-type' };

// @ts-expect-error alert_type is not a public camelCase field
const publicSnake: AlertRuleItem = { ...ruleBase, alert_type: 'price_cross' };

const triggerBase = {
  id: 10,
  target: '600519',
  status: 'triggered' as const,
};
const publicTrigger: AlertTriggerItem = triggerBase;
void publicTrigger;
const naiveTrigger: CamelizeKeys<OpenApiTrigger> = triggerBase;
void naiveTrigger;

void extraParams;
void extraRule;
void extraCreate;
void publicBadType;
void publicSnake;

describe('alerts OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Alerts }).toEqual({});
    expect(Object.keys(Alerts)).toEqual([]);
    expect(Object.getOwnPropertyNames(Alerts)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200 not 201', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiCreatePost200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiCreateBody>().toEqualTypeOf<OpenApiCreate>();
    expectTypeOf<OpenApiGetGet200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiUpdatePatch200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiUpdateBody>().toEqualTypeOf<OpenApiUpdate>();
    expectTypeOf<OpenApiDeleteDelete200>().toEqualTypeOf<OpenApiDelete>();
    expectTypeOf<OpenApiEnablePost200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiDisablePost200>().toEqualTypeOf<OpenApiRule>();
    expectTypeOf<OpenApiTestPost200>().toEqualTypeOf<OpenApiTest>();
    expectTypeOf<OpenApiTriggerListGet200>().toEqualTypeOf<OpenApiTriggerList>();
    expectTypeOf<OpenApiNotificationListGet200>().toEqualTypeOf<OpenApiNotificationList>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiCreateOp>().toEqualTypeOf<OpenApiCreatePathPost>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiGetPathGet>();
    expectTypeOf<OpenApiUpdateOp>().toEqualTypeOf<OpenApiUpdatePathPatch>();
    expectTypeOf<OpenApiDeleteOp>().toEqualTypeOf<OpenApiDeletePathDelete>();
    expectTypeOf<OpenApiEnableOp>().toEqualTypeOf<OpenApiEnablePathPost>();
    expectTypeOf<OpenApiDisableOp>().toEqualTypeOf<OpenApiDisablePathPost>();
    expectTypeOf<OpenApiTestOp>().toEqualTypeOf<OpenApiTestPathPost>();
    expectTypeOf<OpenApiTriggerListOp>().toEqualTypeOf<OpenApiTriggerListPathGet>();
    expectTypeOf<OpenApiNotificationListOp>().toEqualTypeOf<OpenApiNotificationListPathGet>();
    type ListNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type GetNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    type DeleteNeverBody = OpenApiDeleteOp extends { requestBody?: never } ? true : false;
    type EnableNeverBody = OpenApiEnableOp extends { requestBody?: never } ? true : false;
    type DisableNeverBody = OpenApiDisableOp extends { requestBody?: never } ? true : false;
    type TestNeverBody = OpenApiTestOp extends { requestBody?: never } ? true : false;
    type TriggerNeverBody = OpenApiTriggerListOp extends { requestBody?: never } ? true : false;
    type NotificationNeverBody = OpenApiNotificationListOp extends { requestBody?: never } ? true : false;
    type ListHas201 = 201 extends keyof OpenApiListOp['responses'] ? true : false;
    type CreateHas201 = 201 extends keyof OpenApiCreateOp['responses'] ? true : false;
    type GetHas201 = 201 extends keyof OpenApiGetOp['responses'] ? true : false;
    type UpdateHas201 = 201 extends keyof OpenApiUpdateOp['responses'] ? true : false;
    type DeleteHas201 = 201 extends keyof OpenApiDeleteOp['responses'] ? true : false;
    type EnableHas201 = 201 extends keyof OpenApiEnableOp['responses'] ? true : false;
    type DisableHas201 = 201 extends keyof OpenApiDisableOp['responses'] ? true : false;
    type TestHas201 = 201 extends keyof OpenApiTestOp['responses'] ? true : false;
    type TriggerHas201 = 201 extends keyof OpenApiTriggerListOp['responses'] ? true : false;
    type NotificationHas201 = 201 extends keyof OpenApiNotificationListOp['responses'] ? true : false;
    expectTypeOf<ListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<GetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<DeleteNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<EnableNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<DisableNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<TestNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<TriggerNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<NotificationNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ListHas201>().toEqualTypeOf<false>();
    expectTypeOf<CreateHas201>().toEqualTypeOf<false>();
    expectTypeOf<GetHas201>().toEqualTypeOf<false>();
    expectTypeOf<UpdateHas201>().toEqualTypeOf<false>();
    expectTypeOf<DeleteHas201>().toEqualTypeOf<false>();
    expectTypeOf<EnableHas201>().toEqualTypeOf<false>();
    expectTypeOf<DisableHas201>().toEqualTypeOf<false>();
    expectTypeOf<TestHas201>().toEqualTypeOf<false>();
    expectTypeOf<TriggerHas201>().toEqualTypeOf<false>();
    expectTypeOf<NotificationHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public Override types equal path 200 JSON except 1:1 delete', () => {
    type PublicRuleExtendsPath = AlertRuleItem extends OpenApiCreatePost200 ? true : false;
    type PathExtendsPublicRule = OpenApiCreatePost200 extends AlertRuleItem ? true : false;
    type PublicListExtendsPath = AlertRuleListResponse extends OpenApiListGet200 ? true : false;
    type PathExtendsPublicList = OpenApiListGet200 extends AlertRuleListResponse ? true : false;
    type PublicCreateExtendsBody = AlertRuleCreateRequest extends OpenApiCreateBody ? true : false;
    type BodyExtendsPublicCreate = OpenApiCreateBody extends AlertRuleCreateRequest ? true : false;
    type PublicTestExtendsPath = AlertRuleTestResponse extends OpenApiTestPost200 ? true : false;
    type PathExtendsPublicTest = OpenApiTestPost200 extends AlertRuleTestResponse ? true : false;
    type PublicDeleteExtendsPath = AlertDeleteResponse extends OpenApiDeleteDelete200 ? true : false;
    type PathExtendsPublicDelete = OpenApiDeleteDelete200 extends AlertDeleteResponse ? true : false;
    type PublicNotificationExtendsCamel = AlertNotificationItem extends NaiveNotification ? true : false;
    type CamelExtendsPublicNotification = NaiveNotification extends AlertNotificationItem ? true : false;
    type UiTriggerHasSnake = 'alert_type' extends keyof AlertTriggerItem ? true : false;
    type GeneratedTriggerHasCamel = 'alertType' extends keyof OpenApiTrigger ? true : false;
    type UiNotificationHasSnake = 'created_at' extends keyof AlertNotificationItem ? true : false;
    type GeneratedNotificationHasCamel = 'createdAt' extends keyof OpenApiNotification ? true : false;
    expectTypeOf<PublicRuleExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicRule>().toEqualTypeOf<false>();
    expectTypeOf<PublicListExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicList>().toEqualTypeOf<false>();
    expectTypeOf<PublicCreateExtendsBody>().toEqualTypeOf<false>();
    expectTypeOf<BodyExtendsPublicCreate>().toEqualTypeOf<false>();
    expectTypeOf<PublicTestExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicTest>().toEqualTypeOf<false>();
    expectTypeOf<PublicDeleteExtendsPath>().toEqualTypeOf<true>();
    expectTypeOf<PathExtendsPublicDelete>().toEqualTypeOf<true>();
    expectTypeOf<PublicNotificationExtendsCamel>().toEqualTypeOf<true>();
    expectTypeOf<CamelExtendsPublicNotification>().toEqualTypeOf<true>();
    expectTypeOf<UiTriggerHasSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedTriggerHasCamel>().toEqualTypeOf<false>();
    expectTypeOf<UiNotificationHasSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedNotificationHasCamel>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof AlertRuleItem>().not.toMatchTypeOf<'alert_type' | 'target_scope' | 'cooldown_until'>();
    expectTypeOf<keyof AlertRuleListResponse>().not.toMatchTypeOf<'page_size'>();
    expectTypeOf<keyof OpenApiRule>().not.toMatchTypeOf<'alertType' | 'targetScope' | 'cooldownUntil'>();
    expectTypeOf<keyof OpenApiList>().not.toMatchTypeOf<'pageSize'>();
  });

  it('keeps UI list items required while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(listMissingItems).not.toMatchTypeOf<AlertRuleListResponse>();
    expectTypeOf(listMissingItems).toMatchTypeOf<CamelizeKeys<OpenApiList>>();
    expectTypeOf(listMissingItems).not.toMatchTypeOf<AlertTriggerListResponse>();
    expectTypeOf(listMissingItems).toMatchTypeOf<CamelizeKeys<OpenApiTriggerList>>();
    expectTypeOf(listMissingItems).not.toMatchTypeOf<AlertNotificationListResponse>();
    expectTypeOf(listMissingItems).toMatchTypeOf<CamelizeKeys<OpenApiNotificationList>>();
    type UiItemsOptional = IsOptional<AlertRuleListResponse, 'items'>;
    type NaiveItemsOptional = IsOptional<CamelizeKeys<OpenApiList>, 'items'>;
    expectTypeOf<UiItemsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveItemsOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI create enabled and targetScope optional so short create fixtures assign', () => {
    type UiEnabledOptional = IsOptional<AlertRuleCreateRequest, 'enabled'>;
    type UiTargetScopeOptional = IsOptional<AlertRuleCreateRequest, 'targetScope'>;
    type NaiveEnabledOptional = IsOptional<CamelizeKeys<OpenApiCreate>, 'enabled'>;
    type NaiveTargetScopeOptional = IsOptional<CamelizeKeys<OpenApiCreate>, 'targetScope'>;
    expectTypeOf<UiEnabledOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiTargetScopeOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveEnabledOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveTargetScopeOptional>().toEqualTypeOf<false>();
    expectTypeOf(createBase).toMatchTypeOf<AlertRuleCreateRequest>();
    expectTypeOf(createBase).not.toMatchTypeOf<CamelizeKeys<OpenApiCreate>>();
  });

  it('keeps UI test counts optional while naive CamelizeKeys requires them', () => {
    type UiDegradedOptional = IsOptional<AlertRuleTestResponse, 'degradedCount'>;
    type NaiveDegradedOptional = IsOptional<CamelizeKeys<OpenApiTest>, 'degradedCount'>;
    expectTypeOf<UiDegradedOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveDegradedOptional>().toEqualTypeOf<false>();
    expectTypeOf(testMissingCounts).toMatchTypeOf<AlertRuleTestResponse>();
    expectTypeOf(testMissingCounts).not.toMatchTypeOf<CamelizeKeys<OpenApiTest>>();
  });

  it("rejects 'not-a-type' on UI alertType while naive CamelizeKeys accepts string", () => {
    expectTypeOf({ ...ruleBase, alertType: 'not-a-type' }).not.toMatchTypeOf<AlertRuleItem>();
    expectTypeOf({ ...ruleBase, alertType: 'not-a-type' }).toMatchTypeOf<CamelizeKeys<OpenApiRule>>();
    expectTypeOf<'not-a-type'>().not.toMatchTypeOf<AlertRuleItem['alertType']>();
    expectTypeOf<'not-a-type'>().toMatchTypeOf<CamelizeKeys<OpenApiRule>['alertType']>();
  });

  it('keeps AlertRuleParameters closed while naive generated parameters is an open bag', () => {
    type NaiveRuleParams = NonNullable<CamelizeKeys<OpenApiRule>['parameters']>;
    expectTypeOf(naiveParamsExtra).toMatchTypeOf<NaiveRuleParams>();
  });

  it('assigns cooldown bag extras and keeps cooldown_seconds as a wire inner key', () => {
    expectTypeOf(cooldownWithExtra).toMatchTypeOf<AlertCooldownPolicy>();
    expectTypeOf<AlertCooldownPolicy>().toMatchTypeOf<{ cooldown_seconds?: unknown }>();
  });
});
