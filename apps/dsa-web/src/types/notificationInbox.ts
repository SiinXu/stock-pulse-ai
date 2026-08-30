// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

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

type _Assert<T extends true> = T;
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

type _OpenApiAnchors = [
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
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type NotificationInboxKind = OpenApiItem['kind'];
export type NotificationInboxSeverity = OpenApiItem['severity'];
export type NotificationInboxSource = OpenApiSourceStatus['source'];
export type NotificationInboxTitleKey = OpenApiItem['title_key'];

export type NotificationInboxSourceStatus = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiSourceStatus>, {
  source: NotificationInboxSource;
  available: boolean;
  itemCount: number;
  errorCode?: string | null;
}>>;

export type NotificationInboxItem = Override<CamelizeKeys<OpenApiItem>, {
  id: string;
  kind: NotificationInboxKind;
  titleKey: NotificationInboxTitleKey;
  titleParams: Record<string, string>;
  summary: string;
  severity: NotificationInboxSeverity;
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
  metadata?: Record<string, unknown>;
}>;

export type NotificationInboxPage = Override<CamelizeKeys<OpenApiList>, {
  items: NotificationInboxItem[];
  page: number;
  pageSize: number;
  total: number;
  unreadTotal: number;
  cursor?: string | null;
  nextCursor?: string | null;
  hasMore: boolean;
  sourceStatuses: NotificationInboxSourceStatus[];
  retentionDays: number;
  maxItems: number;
}>;

export type NotificationInboxUnreadCount = Override<CamelizeKeys<OpenApiUnread>, {
  unreadTotal: number;
  sourceStatuses: NotificationInboxSourceStatus[];
  retentionDays: number;
  maxItems: number;
}>;

export type NotificationInboxMarkReadResult = Override<CamelizeKeys<OpenApiMarkRead>, {
  markedCount: number;
  unreadTotal: number;
}>;

export type NotificationInboxListQuery = {
  page?: number;
  pageSize?: number;
  cursor?: string;
  kind?: NotificationInboxKind | '';
  unreadOnly?: boolean;
};
