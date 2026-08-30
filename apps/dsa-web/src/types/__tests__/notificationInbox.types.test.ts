// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as NotificationInbox from '../notificationInbox';
import type {
  NotificationInboxItem,
  NotificationInboxKind,
  NotificationInboxListQuery,
  NotificationInboxMarkReadResult,
  NotificationInboxPage,
  NotificationInboxSeverity,
  NotificationInboxSource,
  NotificationInboxSourceStatus,
  NotificationInboxTitleKey,
  NotificationInboxUnreadCount,
} from '../notificationInbox';

type OpenApiItem = components['schemas']['NotificationInboxItem'];
type OpenApiSourceStatus = components['schemas']['NotificationInboxSourceStatus'];
type OpenApiList = components['schemas']['NotificationInboxListResponse'];
type OpenApiUnread = components['schemas']['NotificationInboxUnreadCountResponse'];
type OpenApiMarkRead = components['schemas']['NotificationInboxMarkReadResponse'];
type OpenApiMarkAllRead = components['schemas']['NotificationInboxMarkAllReadResponse'];
type OpenApiMarkReadRequest = components['schemas']['NotificationInboxMarkReadRequest'];
type OpenApiListGet200 =
  operations['list_inbox_items_api_v1_notification_inbox_items_get']['responses']['200']['content']['application/json'];
type OpenApiUnreadGet200 =
  operations['get_inbox_unread_count_api_v1_notification_inbox_unread_count_get']['responses']['200']['content']['application/json'];
type OpenApiMarkReadPost200 =
  operations['mark_inbox_items_read_api_v1_notification_inbox_items_mark_read_post']['responses']['200']['content']['application/json'];
type OpenApiMarkAllPost200 =
  operations['mark_all_inbox_items_read_api_v1_notification_inbox_items_mark_all_read_post']['responses']['200']['content']['application/json'];
type OpenApiMarkReadBody =
  operations['mark_inbox_items_read_api_v1_notification_inbox_items_mark_read_post']['requestBody']['content']['application/json'];
type OpenApiListPathGet = paths['/api/v1/notification-inbox/items']['get'];
type OpenApiUnreadPathGet = paths['/api/v1/notification-inbox/unread-count']['get'];
type OpenApiMarkReadPathPost = paths['/api/v1/notification-inbox/items/mark-read']['post'];
type OpenApiMarkAllPathPost = paths['/api/v1/notification-inbox/items/mark-all-read']['post'];
type OpenApiListOp = operations['list_inbox_items_api_v1_notification_inbox_items_get'];
type OpenApiUnreadOp = operations['get_inbox_unread_count_api_v1_notification_inbox_unread_count_get'];
type OpenApiMarkReadOp = operations['mark_inbox_items_read_api_v1_notification_inbox_items_mark_read_post'];
type OpenApiMarkAllOp = operations['mark_all_inbox_items_read_api_v1_notification_inbox_items_mark_all_read_post'];
type OpenApiQuery = NonNullable<OpenApiListOp['parameters']['query']>;

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type CamelQuery = CamelizeKeys<OpenApiQuery>;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiList ? true : false>;
type _ListIsList200 = _Assert<OpenApiList extends OpenApiListGet200 ? true : false>;
type _Unread200IsUnread = _Assert<OpenApiUnreadGet200 extends OpenApiUnread ? true : false>;
type _UnreadIsUnread200 = _Assert<OpenApiUnread extends OpenApiUnreadGet200 ? true : false>;
type _MarkRead200IsMark = _Assert<OpenApiMarkReadPost200 extends OpenApiMarkRead ? true : false>;
type _MarkIsMarkRead200 = _Assert<OpenApiMarkRead extends OpenApiMarkReadPost200 ? true : false>;
type _MarkAll200IsMarkAll = _Assert<OpenApiMarkAllPost200 extends OpenApiMarkAllRead ? true : false>;
type _MarkAllIsMarkAll200 = _Assert<OpenApiMarkAllRead extends OpenApiMarkAllPost200 ? true : false>;
type _MarkReadBodyIsRequest = _Assert<OpenApiMarkReadBody extends OpenApiMarkReadRequest ? true : false>;
type _RequestIsMarkReadBody = _Assert<OpenApiMarkReadRequest extends OpenApiMarkReadBody ? true : false>;
type _MarkReadIsMarkAll = _Assert<OpenApiMarkRead extends OpenApiMarkAllRead ? true : false>;
type _MarkAllIsMarkRead = _Assert<OpenApiMarkAllRead extends OpenApiMarkRead ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _ListPathIsOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _UnreadOpIsPath = _Assert<OpenApiUnreadOp extends OpenApiUnreadPathGet ? true : false>;
type _UnreadPathIsOp = _Assert<OpenApiUnreadPathGet extends OpenApiUnreadOp ? true : false>;
type _MarkReadOpIsPath = _Assert<OpenApiMarkReadOp extends OpenApiMarkReadPathPost ? true : false>;
type _MarkReadPathIsOp = _Assert<OpenApiMarkReadPathPost extends OpenApiMarkReadOp ? true : false>;
type _MarkAllOpIsPath = _Assert<OpenApiMarkAllOp extends OpenApiMarkAllPathPost ? true : false>;
type _MarkAllPathIsOp = _Assert<OpenApiMarkAllPathPost extends OpenApiMarkAllOp ? true : false>;
type _ListOpHasNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _UnreadOpHasNeverRequestBody = _Assert<OpenApiUnreadOp extends { requestBody?: never } ? true : false>;
type _ListPathPostNever = _Assert<
  paths['/api/v1/notification-inbox/items']['post'] extends never | undefined ? true : false
>;
type _UnreadPathPostNever = _Assert<
  paths['/api/v1/notification-inbox/unread-count']['post'] extends never | undefined ? true : false
>;
type _List200IsNotItem = _Assert<OpenApiListGet200 extends OpenApiItem ? false : true>;
type _Unread200IsNotList = _Assert<OpenApiUnreadGet200 extends OpenApiList ? false : true>;
type _List200HasItems = _Assert<'items' extends keyof OpenApiListGet200 ? true : false>;
type _MarkBodyHasItemIds = _Assert<'item_ids' extends keyof OpenApiMarkReadBody ? true : false>;
type _List200LacksItemIds = _Assert<'item_ids' extends keyof OpenApiListGet200 ? false : true>;
type _MarkBodyLacksItems = _Assert<'items' extends keyof OpenApiMarkReadBody ? false : true>;

type _UiHasTitleKey = _Assert<'titleKey' extends keyof NotificationInboxItem ? true : false>;
type _UiHasTitleParams = _Assert<'titleParams' extends keyof NotificationInboxItem ? true : false>;
type _UiHasCreatedAt = _Assert<'createdAt' extends keyof NotificationInboxItem ? true : false>;
type _UiHasIsRead = _Assert<'isRead' extends keyof NotificationInboxItem ? true : false>;
type _UiHasSourceId = _Assert<'sourceId' extends keyof NotificationInboxItem ? true : false>;
type _UiHasPageSize = _Assert<'pageSize' extends keyof NotificationInboxPage ? true : false>;
type _UiHasUnreadTotal = _Assert<'unreadTotal' extends keyof NotificationInboxPage ? true : false>;
type _UiHasHasMore = _Assert<'hasMore' extends keyof NotificationInboxPage ? true : false>;
type _UiHasSourceStatuses = _Assert<'sourceStatuses' extends keyof NotificationInboxPage ? true : false>;
type _UiHasRetentionDays = _Assert<'retentionDays' extends keyof NotificationInboxPage ? true : false>;
type _UiHasMaxItems = _Assert<'maxItems' extends keyof NotificationInboxPage ? true : false>;
type _UiHasItemCount = _Assert<'itemCount' extends keyof NotificationInboxSourceStatus ? true : false>;
type _UiHasErrorCode = _Assert<'errorCode' extends keyof NotificationInboxSourceStatus ? true : false>;
type _UiHasMarkedCount = _Assert<'markedCount' extends keyof NotificationInboxMarkReadResult ? true : false>;
type _UiHasResultUnreadTotal = _Assert<'unreadTotal' extends keyof NotificationInboxMarkReadResult ? true : false>;
type _UiUnreadHasSourceStatuses = _Assert<'sourceStatuses' extends keyof NotificationInboxUnreadCount ? true : false>;
type _UiQueryHasPageSize = _Assert<'pageSize' extends keyof NotificationInboxListQuery ? true : false>;
type _UiQueryHasUnreadOnly = _Assert<'unreadOnly' extends keyof NotificationInboxListQuery ? true : false>;

type _UiLacksTitleKeySnake = _Assert<'title_key' extends keyof NotificationInboxItem ? false : true>;
type _UiLacksTitleParamsSnake = _Assert<'title_params' extends keyof NotificationInboxItem ? false : true>;
type _UiLacksCreatedAtSnake = _Assert<'created_at' extends keyof NotificationInboxItem ? false : true>;
type _UiLacksIsReadSnake = _Assert<'is_read' extends keyof NotificationInboxItem ? false : true>;
type _UiLacksSourceIdSnake = _Assert<'source_id' extends keyof NotificationInboxItem ? false : true>;
type _UiLacksPageSizeSnake = _Assert<'page_size' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksUnreadTotalSnake = _Assert<'unread_total' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksHasMoreSnake = _Assert<'has_more' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksSourceStatusesSnake = _Assert<'source_statuses' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksRetentionDaysSnake = _Assert<'retention_days' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksMaxItemsSnake = _Assert<'max_items' extends keyof NotificationInboxPage ? false : true>;
type _UiLacksItemCountSnake = _Assert<'item_count' extends keyof NotificationInboxSourceStatus ? false : true>;
type _UiLacksErrorCodeSnake = _Assert<'error_code' extends keyof NotificationInboxSourceStatus ? false : true>;
type _UiLacksMarkedCountSnake = _Assert<'marked_count' extends keyof NotificationInboxMarkReadResult ? false : true>;
type _UiQueryLacksPageSizeSnake = _Assert<'page_size' extends keyof NotificationInboxListQuery ? false : true>;
type _UiQueryLacksUnreadOnlySnake = _Assert<'unread_only' extends keyof NotificationInboxListQuery ? false : true>;

type _GeneratedHasTitleKeySnake = _Assert<'title_key' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasTitleParamsSnake = _Assert<'title_params' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasCreatedAtSnake = _Assert<'created_at' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasIsReadSnake = _Assert<'is_read' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasSourceIdSnake = _Assert<'source_id' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiList ? true : false>;
type _GeneratedHasUnreadTotalSnake = _Assert<'unread_total' extends keyof OpenApiList ? true : false>;
type _GeneratedHasHasMoreSnake = _Assert<'has_more' extends keyof OpenApiList ? true : false>;
type _GeneratedHasSourceStatusesSnake = _Assert<'source_statuses' extends keyof OpenApiList ? true : false>;
type _GeneratedHasRetentionDaysSnake = _Assert<'retention_days' extends keyof OpenApiList ? true : false>;
type _GeneratedHasMaxItemsSnake = _Assert<'max_items' extends keyof OpenApiList ? true : false>;
type _GeneratedHasItemCountSnake = _Assert<'item_count' extends keyof OpenApiSourceStatus ? true : false>;
type _GeneratedHasErrorCodeSnake = _Assert<'error_code' extends keyof OpenApiSourceStatus ? true : false>;
type _GeneratedHasMarkedCountSnake = _Assert<'marked_count' extends keyof OpenApiMarkRead ? true : false>;
type _GeneratedQueryHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiQuery ? true : false>;
type _GeneratedQueryHasUnreadOnlySnake = _Assert<'unread_only' extends keyof OpenApiQuery ? true : false>;
type _GeneratedBodyHasItemIdsSnake = _Assert<'item_ids' extends keyof OpenApiMarkReadRequest ? true : false>;

type _UiLacksTitleKeyCamelOnGenerated = _Assert<'titleKey' extends keyof OpenApiItem ? false : true>;
type _UiLacksPageSizeCamelOnGenerated = _Assert<'pageSize' extends keyof OpenApiList ? false : true>;
type _UiLacksSourceStatusesCamelOnGenerated = _Assert<'sourceStatuses' extends keyof OpenApiList ? false : true>;
type _UiLacksTitleParamsCamelOnGenerated = _Assert<'titleParams' extends keyof OpenApiItem ? false : true>;

type _UiTitleParamsRequired = _Assert<IsOptional<NotificationInboxItem, 'titleParams'> extends false ? true : false>;
type _GeneratedTitleParamsOptional = _Assert<IsOptional<OpenApiItem, 'title_params'>>;
type _UiSourceStatusesRequired = _Assert<
  IsOptional<NotificationInboxPage, 'sourceStatuses'> extends false ? true : false
>;
type _GeneratedSourceStatusesOptional = _Assert<IsOptional<OpenApiList, 'source_statuses'>>;
type _UiUnreadSourceStatusesRequired = _Assert<
  IsOptional<NotificationInboxUnreadCount, 'sourceStatuses'> extends false ? true : false
>;
type _GeneratedUnreadSourceStatusesOptional = _Assert<IsOptional<OpenApiUnread, 'source_statuses'>>;
type _UiMetadataOptional = _Assert<IsOptional<NotificationInboxItem, 'metadata'>>;
type _GeneratedMetadataOptional = _Assert<IsOptional<OpenApiItem, 'metadata'>>;
type _UiItemsRequired = _Assert<IsOptional<NotificationInboxPage, 'items'> extends false ? true : false>;
type _UiPageRequired = _Assert<IsOptional<NotificationInboxPage, 'page'> extends false ? true : false>;
type _UiPageSizeRequired = _Assert<IsOptional<NotificationInboxPage, 'pageSize'> extends false ? true : false>;
type _UiTotalRequired = _Assert<IsOptional<NotificationInboxPage, 'total'> extends false ? true : false>;
type _UiIdRequired = _Assert<IsOptional<NotificationInboxItem, 'id'> extends false ? true : false>;
type _UiKindRequired = _Assert<IsOptional<NotificationInboxItem, 'kind'> extends false ? true : false>;
type _UiQueryPageOptional = _Assert<IsOptional<NotificationInboxListQuery, 'page'>>;
type _UiQueryPageSizeOptional = _Assert<IsOptional<NotificationInboxListQuery, 'pageSize'>>;
type _UiQueryKindOptional = _Assert<IsOptional<NotificationInboxListQuery, 'kind'>>;
type _UiQueryUnreadOnlyOptional = _Assert<IsOptional<NotificationInboxListQuery, 'unreadOnly'>>;
type _UiCursorOptional = _Assert<IsOptional<NotificationInboxPage, 'cursor'>>;
type _UiNextCursorOptional = _Assert<IsOptional<NotificationInboxPage, 'nextCursor'>>;

type _OmitTitleParams = _Assert<Omit<NotificationInboxItem, 'titleParams'> extends NotificationInboxItem ? false : true>;
type _OmitGeneratedTitleParams = _Assert<Omit<OpenApiItem, 'title_params'> extends OpenApiItem ? true : false>;
type _OmitSourceStatuses = _Assert<
  Omit<NotificationInboxPage, 'sourceStatuses'> extends NotificationInboxPage ? false : true
>;
type _OmitGeneratedSourceStatuses = _Assert<Omit<OpenApiList, 'source_statuses'> extends OpenApiList ? true : false>;
type _OmitMetadata = _Assert<Omit<NotificationInboxItem, 'metadata'> extends NotificationInboxItem ? true : false>;
type _OmitPageSize = _Assert<Omit<NotificationInboxPage, 'pageSize'> extends NotificationInboxPage ? false : true>;
type _OmitGeneratedPageSize = _Assert<Omit<OpenApiList, 'page_size'> extends OpenApiList ? false : true>;
type _OmitItems = _Assert<Omit<NotificationInboxPage, 'items'> extends NotificationInboxPage ? false : true>;

type _StringKindRejected = _Assert<string extends NotificationInboxKind ? false : true>;
type _AnalysisCompleteAssignable = _Assert<'analysis_complete' extends NotificationInboxKind ? true : false>;
type _AlertTriggeredAssignable = _Assert<'alert_triggered' extends NotificationInboxKind ? true : false>;
type _StringSeverityRejected = _Assert<string extends NotificationInboxSeverity ? false : true>;
type _InfoSeverityAssignable = _Assert<'info' extends NotificationInboxSeverity ? true : false>;
type _WarningSeverityAssignable = _Assert<'warning' extends NotificationInboxSeverity ? true : false>;
type _StringSourceRejected = _Assert<string extends NotificationInboxSource ? false : true>;
type _AnalysisSourceAssignable = _Assert<'analysis' extends NotificationInboxSource ? true : false>;
type _StringTitleKeyRejected = _Assert<string extends NotificationInboxTitleKey ? false : true>;
type _AnalysisCompleteTitleAssignable = _Assert<
  'analysisCompleteTitle' extends NotificationInboxTitleKey ? true : false
>;

type _GeneratedQueryAllowsKindNull = _Assert<null extends OpenApiQuery['kind'] ? true : false>;
type _GeneratedQueryAllowsCursorNull = _Assert<null extends OpenApiQuery['cursor'] ? true : false>;
type _CamelQueryAllowsKindNull = _Assert<null extends CamelQuery['kind'] ? true : false>;
type _CamelQueryAllowsCursorNull = _Assert<null extends CamelQuery['cursor'] ? true : false>;
type _UiQueryRejectsKindNull = _Assert<null extends NotificationInboxListQuery['kind'] ? false : true>;
type _UiQueryRejectsCursorNull = _Assert<null extends NotificationInboxListQuery['cursor'] ? false : true>;
type _UiQueryAllowsEmptyKind = _Assert<'' extends NonNullable<NotificationInboxListQuery['kind']> ? true : false>;
type _UiQueryRejectsStringKind = _Assert<string extends NotificationInboxListQuery['kind'] ? false : true>;

type NarrowStatus = {
  source: 'analysis';
  available: boolean;
  itemCount: number;
};
type NarrowItem = {
  id: string;
  kind: 'analysis_complete';
  titleKey: 'analysisCompleteTitle';
  titleParams: Record<string, string>;
  summary: string;
  severity: 'info';
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
};
type NarrowAlertItem = {
  id: string;
  kind: 'alert_triggered';
  titleKey: 'alertTriggeredTitle';
  titleParams: Record<string, string>;
  summary: string;
  severity: 'warning';
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
};
type NarrowPage = {
  items: NarrowItem[];
  page: number;
  pageSize: number;
  total: number;
  unreadTotal: number;
  hasMore: boolean;
  sourceStatuses: NarrowStatus[];
  retentionDays: number;
  maxItems: number;
};
type NarrowUnread = {
  unreadTotal: number;
  sourceStatuses: NarrowStatus[];
  retentionDays: number;
  maxItems: number;
};
type NarrowMark = {
  markedCount: number;
  unreadTotal: number;
};
type NarrowQuery = {
  page: number;
  pageSize: number;
  cursor: string;
  kind: '';
  unreadOnly: boolean;
};

type _NarrowStatusAssignable = _Assert<NarrowStatus extends NotificationInboxSourceStatus ? true : false>;
type _NarrowItemAssignable = _Assert<NarrowItem extends NotificationInboxItem ? true : false>;
type _NarrowAlertAssignable = _Assert<NarrowAlertItem extends NotificationInboxItem ? true : false>;
type _NarrowPageAssignable = _Assert<NarrowPage extends NotificationInboxPage ? true : false>;
type _NarrowUnreadAssignable = _Assert<NarrowUnread extends NotificationInboxUnreadCount ? true : false>;
type _NarrowMarkAssignable = _Assert<NarrowMark extends NotificationInboxMarkReadResult ? true : false>;
type _NarrowQueryAssignable = _Assert<NarrowQuery extends NotificationInboxListQuery ? true : false>;

type MysteryKindItem = {
  id: string;
  kind: string;
  titleKey: 'analysisCompleteTitle';
  titleParams: Record<string, string>;
  summary: string;
  severity: 'info';
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
};
type MysterySeverityItem = {
  id: string;
  kind: 'analysis_complete';
  titleKey: 'analysisCompleteTitle';
  titleParams: Record<string, string>;
  summary: string;
  severity: string;
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
};
type MysterySourceStatus = {
  source: string;
  available: boolean;
  itemCount: number;
};
type MysteryTitleKeyItem = {
  id: string;
  kind: 'analysis_complete';
  titleKey: string;
  titleParams: Record<string, string>;
  summary: string;
  severity: 'info';
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
};
type _MysteryKindRejected = _Assert<MysteryKindItem extends NotificationInboxItem ? false : true>;
type _MysterySeverityRejected = _Assert<MysterySeverityItem extends NotificationInboxItem ? false : true>;
type _MysterySourceRejected = _Assert<MysterySourceStatus extends NotificationInboxSourceStatus ? false : true>;
type _MysteryTitleKeyRejected = _Assert<MysteryTitleKeyItem extends NotificationInboxItem ? false : true>;

type SnakeItem = {
  id: string;
  kind: 'analysis_complete';
  title_key: 'analysisCompleteTitle';
  summary: string;
  severity: 'info';
  created_at: string;
  is_read: boolean;
  href: string;
  source_id: string;
};
type SnakePage = {
  items: OpenApiItem[];
  page: number;
  page_size: number;
  total: number;
  unread_total: number;
  has_more: boolean;
  max_items: number;
  retention_days: number;
};
type SnakeMark = {
  marked_count: number;
  unread_total: number;
};
type _SnakeItemMatchesGenerated = _Assert<SnakeItem extends OpenApiItem ? true : false>;
type _SnakeItemDoesNotMatchUi = _Assert<SnakeItem extends NotificationInboxItem ? false : true>;
type _SnakePageMatchesGenerated = _Assert<SnakePage extends OpenApiList ? true : false>;
type _SnakePageDoesNotMatchUi = _Assert<SnakePage extends NotificationInboxPage ? false : true>;
type _SnakeMarkMatchesGenerated = _Assert<SnakeMark extends OpenApiMarkRead ? true : false>;
type _SnakeMarkDoesNotMatchUi = _Assert<SnakeMark extends NotificationInboxMarkReadResult ? false : true>;
type _UiPageIsNotGeneratedAlias = _Assert<NotificationInboxPage extends OpenApiList ? false : true>;
type _GeneratedPageIsNotUi = _Assert<OpenApiList extends NotificationInboxPage ? false : true>;
type _UiItemIsNotGeneratedAlias = _Assert<NotificationInboxItem extends OpenApiItem ? false : true>;
type _UiMarkIsNotGeneratedAlias = _Assert<NotificationInboxMarkReadResult extends OpenApiMarkRead ? false : true>;

type _CompileTimePins = [
  _List200IsList,
  _ListIsList200,
  _Unread200IsUnread,
  _UnreadIsUnread200,
  _MarkRead200IsMark,
  _MarkIsMarkRead200,
  _MarkAll200IsMarkAll,
  _MarkAllIsMarkAll200,
  _MarkReadBodyIsRequest,
  _RequestIsMarkReadBody,
  _MarkReadIsMarkAll,
  _MarkAllIsMarkRead,
  _ListOpIsPath,
  _ListPathIsOp,
  _UnreadOpIsPath,
  _UnreadPathIsOp,
  _MarkReadOpIsPath,
  _MarkReadPathIsOp,
  _MarkAllOpIsPath,
  _MarkAllPathIsOp,
  _ListOpHasNeverRequestBody,
  _UnreadOpHasNeverRequestBody,
  _ListPathPostNever,
  _UnreadPathPostNever,
  _List200IsNotItem,
  _Unread200IsNotList,
  _List200HasItems,
  _MarkBodyHasItemIds,
  _List200LacksItemIds,
  _MarkBodyLacksItems,
  _UiHasTitleKey,
  _UiHasTitleParams,
  _UiHasCreatedAt,
  _UiHasIsRead,
  _UiHasSourceId,
  _UiHasPageSize,
  _UiHasUnreadTotal,
  _UiHasHasMore,
  _UiHasSourceStatuses,
  _UiHasRetentionDays,
  _UiHasMaxItems,
  _UiHasItemCount,
  _UiHasErrorCode,
  _UiHasMarkedCount,
  _UiHasResultUnreadTotal,
  _UiUnreadHasSourceStatuses,
  _UiQueryHasPageSize,
  _UiQueryHasUnreadOnly,
  _UiLacksTitleKeySnake,
  _UiLacksTitleParamsSnake,
  _UiLacksCreatedAtSnake,
  _UiLacksIsReadSnake,
  _UiLacksSourceIdSnake,
  _UiLacksPageSizeSnake,
  _UiLacksUnreadTotalSnake,
  _UiLacksHasMoreSnake,
  _UiLacksSourceStatusesSnake,
  _UiLacksRetentionDaysSnake,
  _UiLacksMaxItemsSnake,
  _UiLacksItemCountSnake,
  _UiLacksErrorCodeSnake,
  _UiLacksMarkedCountSnake,
  _UiQueryLacksPageSizeSnake,
  _UiQueryLacksUnreadOnlySnake,
  _GeneratedHasTitleKeySnake,
  _GeneratedHasTitleParamsSnake,
  _GeneratedHasCreatedAtSnake,
  _GeneratedHasIsReadSnake,
  _GeneratedHasSourceIdSnake,
  _GeneratedHasPageSizeSnake,
  _GeneratedHasUnreadTotalSnake,
  _GeneratedHasHasMoreSnake,
  _GeneratedHasSourceStatusesSnake,
  _GeneratedHasRetentionDaysSnake,
  _GeneratedHasMaxItemsSnake,
  _GeneratedHasItemCountSnake,
  _GeneratedHasErrorCodeSnake,
  _GeneratedHasMarkedCountSnake,
  _GeneratedQueryHasPageSizeSnake,
  _GeneratedQueryHasUnreadOnlySnake,
  _GeneratedBodyHasItemIdsSnake,
  _UiLacksTitleKeyCamelOnGenerated,
  _UiLacksPageSizeCamelOnGenerated,
  _UiLacksSourceStatusesCamelOnGenerated,
  _UiLacksTitleParamsCamelOnGenerated,
  _UiTitleParamsRequired,
  _GeneratedTitleParamsOptional,
  _UiSourceStatusesRequired,
  _GeneratedSourceStatusesOptional,
  _UiUnreadSourceStatusesRequired,
  _GeneratedUnreadSourceStatusesOptional,
  _UiMetadataOptional,
  _GeneratedMetadataOptional,
  _UiItemsRequired,
  _UiPageRequired,
  _UiPageSizeRequired,
  _UiTotalRequired,
  _UiIdRequired,
  _UiKindRequired,
  _UiQueryPageOptional,
  _UiQueryPageSizeOptional,
  _UiQueryKindOptional,
  _UiQueryUnreadOnlyOptional,
  _UiCursorOptional,
  _UiNextCursorOptional,
  _OmitTitleParams,
  _OmitGeneratedTitleParams,
  _OmitSourceStatuses,
  _OmitGeneratedSourceStatuses,
  _OmitMetadata,
  _OmitPageSize,
  _OmitGeneratedPageSize,
  _OmitItems,
  _StringKindRejected,
  _AnalysisCompleteAssignable,
  _AlertTriggeredAssignable,
  _StringSeverityRejected,
  _InfoSeverityAssignable,
  _WarningSeverityAssignable,
  _StringSourceRejected,
  _AnalysisSourceAssignable,
  _StringTitleKeyRejected,
  _AnalysisCompleteTitleAssignable,
  _GeneratedQueryAllowsKindNull,
  _GeneratedQueryAllowsCursorNull,
  _CamelQueryAllowsKindNull,
  _CamelQueryAllowsCursorNull,
  _UiQueryRejectsKindNull,
  _UiQueryRejectsCursorNull,
  _UiQueryAllowsEmptyKind,
  _UiQueryRejectsStringKind,
  _NarrowStatusAssignable,
  _NarrowItemAssignable,
  _NarrowAlertAssignable,
  _NarrowPageAssignable,
  _NarrowUnreadAssignable,
  _NarrowMarkAssignable,
  _NarrowQueryAssignable,
  _MysteryKindRejected,
  _MysterySeverityRejected,
  _MysterySourceRejected,
  _MysteryTitleKeyRejected,
  _SnakeItemMatchesGenerated,
  _SnakeItemDoesNotMatchUi,
  _SnakePageMatchesGenerated,
  _SnakePageDoesNotMatchUi,
  _SnakeMarkMatchesGenerated,
  _SnakeMarkDoesNotMatchUi,
  _UiPageIsNotGeneratedAlias,
  _GeneratedPageIsNotUi,
  _UiItemIsNotGeneratedAlias,
  _UiMarkIsNotGeneratedAlias,
];

describe('notificationInbox OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...NotificationInbox }).toEqual({});
    expect(Object.keys(NotificationInbox)).toEqual([]);
    expect(Object.getOwnPropertyNames(NotificationInbox)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON and mark-read body to the generated components', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiUnreadGet200>().toEqualTypeOf<OpenApiUnread>();
    expectTypeOf<OpenApiMarkReadPost200>().toEqualTypeOf<OpenApiMarkRead>();
    expectTypeOf<OpenApiMarkAllPost200>().toEqualTypeOf<OpenApiMarkAllRead>();
    expectTypeOf<OpenApiMarkRead>().toEqualTypeOf<OpenApiMarkAllRead>();
    expectTypeOf<OpenApiMarkReadBody>().toEqualTypeOf<OpenApiMarkReadRequest>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiUnreadOp>().toEqualTypeOf<OpenApiUnreadPathGet>();
    expectTypeOf<OpenApiMarkReadOp>().toEqualTypeOf<OpenApiMarkReadPathPost>();
    expectTypeOf<OpenApiMarkAllOp>().toEqualTypeOf<OpenApiMarkAllPathPost>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof NotificationInboxItem>().not.toMatchTypeOf<
      'title_key' | 'title_params' | 'created_at' | 'is_read' | 'source_id'
    >();
    expectTypeOf<keyof NotificationInboxPage>().not.toMatchTypeOf<
      'page_size' | 'unread_total' | 'has_more' | 'source_statuses' | 'retention_days' | 'max_items'
    >();
    expectTypeOf<keyof NotificationInboxListQuery>().not.toMatchTypeOf<'page_size' | 'unread_only'>();

    type UiHasTitleKey = 'titleKey' extends keyof NotificationInboxItem ? true : false;
    type UiHasTitleKeySnake = 'title_key' extends keyof NotificationInboxItem ? true : false;
    type GeneratedHasTitleKeySnake = 'title_key' extends keyof OpenApiItem ? true : false;
    type UiHasPageSize = 'pageSize' extends keyof NotificationInboxPage ? true : false;
    type UiHasPageSizeSnake = 'page_size' extends keyof NotificationInboxPage ? true : false;
    type GeneratedHasPageSizeSnake = 'page_size' extends keyof OpenApiList ? true : false;
    type UiHasSourceStatuses = 'sourceStatuses' extends keyof NotificationInboxPage ? true : false;
    type UiHasSourceStatusesSnake = 'source_statuses' extends keyof NotificationInboxPage ? true : false;
    type GeneratedHasSourceStatusesSnake = 'source_statuses' extends keyof OpenApiList ? true : false;

    expectTypeOf<UiHasTitleKey>().toEqualTypeOf<true>();
    expectTypeOf<UiHasTitleKeySnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasTitleKeySnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSize>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSizeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPageSizeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSourceStatuses>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSourceStatusesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSourceStatusesSnake>().toEqualTypeOf<true>();
  });

  it('keeps titleParams and sourceStatuses required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<NotificationInboxItem, 'titleParams'>>().not.toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf<Omit<OpenApiItem, 'title_params'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<NotificationInboxPage, 'sourceStatuses'>>().not.toMatchTypeOf<NotificationInboxPage>();
    expectTypeOf<Omit<OpenApiList, 'source_statuses'>>().toMatchTypeOf<OpenApiList>();
    expectTypeOf<Omit<NotificationInboxUnreadCount, 'sourceStatuses'>>().not.toMatchTypeOf<
      NotificationInboxUnreadCount
    >();
    expectTypeOf<Omit<OpenApiUnread, 'source_statuses'>>().toMatchTypeOf<OpenApiUnread>();
    expectTypeOf<Omit<NotificationInboxItem, 'metadata'>>().toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf<Omit<NotificationInboxPage, 'pageSize'>>().not.toMatchTypeOf<NotificationInboxPage>();
  });

  it('rejects illegal enum widening on kind, severity, source, and titleKey', () => {
    expectTypeOf({
      id: 'v1:analysis_complete:1:1',
      kind: 'mystery' as string,
      titleKey: 'analysisCompleteTitle' as const,
      titleParams: { label: 'AAPL' },
      summary: 'hold',
      severity: 'info' as const,
      createdAt: '2026-08-10T00:00:00Z',
      isRead: false,
      href: '/research',
      sourceId: '1',
    }).not.toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf({
      id: 'v1:analysis_complete:1:1',
      kind: 'analysis_complete' as const,
      titleKey: 'analysisCompleteTitle' as const,
      titleParams: { label: 'AAPL' },
      summary: 'hold',
      severity: 'mystery' as string,
      createdAt: '2026-08-10T00:00:00Z',
      isRead: false,
      href: '/research',
      sourceId: '1',
    }).not.toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf({
      source: 'mystery' as string,
      available: true,
      itemCount: 1,
    }).not.toMatchTypeOf<NotificationInboxSourceStatus>();
    expectTypeOf({
      id: 'v1:analysis_complete:1:1',
      kind: 'analysis_complete' as const,
      titleKey: 'mystery' as string,
      titleParams: { label: 'AAPL' },
      summary: 'hold',
      severity: 'info' as const,
      createdAt: '2026-08-10T00:00:00Z',
      isRead: false,
      href: '/research',
      sourceId: '1',
    }).not.toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf<string>().not.toMatchTypeOf<NotificationInboxKind>();
    expectTypeOf<string>().not.toMatchTypeOf<NotificationInboxSeverity>();
    expectTypeOf<string>().not.toMatchTypeOf<NotificationInboxSource>();
    expectTypeOf<string>().not.toMatchTypeOf<NotificationInboxTitleKey>();
    expectTypeOf<'analysis_complete'>().toMatchTypeOf<NotificationInboxKind>();
    expectTypeOf<'info'>().toMatchTypeOf<NotificationInboxSeverity>();
    expectTypeOf<'analysis'>().toMatchTypeOf<NotificationInboxSource>();
    expectTypeOf<'analysisCompleteTitle'>().toMatchTypeOf<NotificationInboxTitleKey>();
  });

  it('still accepts the narrow existing fixtures, including omitted metadata', () => {
    const item: NotificationInboxItem = {
      id: 'v1:analysis_complete:1:1786233600000000',
      kind: 'analysis_complete',
      titleKey: 'analysisCompleteTitle',
      titleParams: { label: '600519' },
      summary: 'hold',
      severity: 'info',
      createdAt: '2026-08-09T00:00:00Z',
      isRead: false,
      href: '/research/analysis?segment=history&recordId=1',
      sourceId: '1',
    };
    const alert: NotificationInboxItem = {
      ...item,
      id: 'v1:alert_triggered:2:1786233500000000',
      kind: 'alert_triggered',
      titleKey: 'alertTriggeredTitle',
      titleParams: { target: 'MSFT' },
      summary: 'Threshold crossed',
      severity: 'warning',
      href: '/signals?tab=history&trigger=2',
      sourceId: '2',
    };
    const page: NotificationInboxPage = {
      items: [item, alert],
      page: 1,
      pageSize: 50,
      total: 2,
      unreadTotal: 1,
      hasMore: false,
      sourceStatuses: [
        { source: 'analysis', available: true, itemCount: 1 },
        { source: 'alerts', available: true, itemCount: 1 },
      ],
      retentionDays: 90,
      maxItems: 500,
    };
    const unread: NotificationInboxUnreadCount = {
      unreadTotal: 1,
      sourceStatuses: page.sourceStatuses,
      retentionDays: 90,
      maxItems: 500,
    };
    const mark: NotificationInboxMarkReadResult = {
      markedCount: 1,
      unreadTotal: 0,
    };
    const query: NotificationInboxListQuery = {
      page: 1,
      pageSize: 50,
      cursor: 'abc',
      kind: '',
      unreadOnly: true,
    };
    expectTypeOf(item).toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf(alert).toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf(page).toMatchTypeOf<NotificationInboxPage>();
    expectTypeOf(unread).toMatchTypeOf<NotificationInboxUnreadCount>();
    expectTypeOf(mark).toMatchTypeOf<NotificationInboxMarkReadResult>();
    expectTypeOf(query).toMatchTypeOf<NotificationInboxListQuery>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeItem = {
      id: 'v1:analysis_complete:1:1',
      kind: 'analysis_complete' as const,
      title_key: 'analysisCompleteTitle' as const,
      summary: 'hold',
      severity: 'info' as const,
      created_at: '2026-08-09T00:00:00Z',
      is_read: false,
      href: '/research',
      source_id: '1',
    };
    const snakePage = {
      items: [] as OpenApiItem[],
      page: 1,
      page_size: 50,
      total: 0,
      unread_total: 0,
      has_more: false,
      max_items: 500,
      retention_days: 90,
    };
    const snakeMark = {
      marked_count: 1,
      unread_total: 0,
    };
    expectTypeOf(snakeItem).toMatchTypeOf<OpenApiItem>();
    expectTypeOf(snakeItem).not.toMatchTypeOf<NotificationInboxItem>();
    expectTypeOf(snakePage).toMatchTypeOf<OpenApiList>();
    expectTypeOf(snakePage).not.toMatchTypeOf<NotificationInboxPage>();
    expectTypeOf(snakeMark).toMatchTypeOf<OpenApiMarkRead>();
    expectTypeOf(snakeMark).not.toMatchTypeOf<NotificationInboxMarkReadResult>();
  });

  it('does not bind NotificationInboxListQuery from generated query nullability', () => {
    const nullQuery = {
      kind: null,
      cursor: null,
    };
    expectTypeOf(nullQuery).not.toMatchTypeOf<NotificationInboxListQuery>();
    expectTypeOf<null>().toMatchTypeOf<OpenApiQuery['kind']>();
    expectTypeOf<null>().not.toMatchTypeOf<NotificationInboxListQuery['kind']>();
    expectTypeOf<null>().not.toMatchTypeOf<NotificationInboxListQuery['cursor']>();
    expectTypeOf<''>().toMatchTypeOf<NonNullable<NotificationInboxListQuery['kind']>>();
  });
});
