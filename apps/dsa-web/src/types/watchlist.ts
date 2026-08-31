// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { StockBarItem, TaskInfo } from './analysis';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiComputedAttrs = components['schemas']['WatchlistComputedAttrsSchema'];
type OpenApiMember = components['schemas']['WatchlistGroupMemberSchema'];
type OpenApiGroup = components['schemas']['WatchlistGroupSchema'];
type OpenApiGroupsResponse = components['schemas']['WatchlistGroupsResponse'];
type OpenApiCreateRequest = components['schemas']['WatchlistGroupCreateRequest'];
type OpenApiRestoreRequest = components['schemas']['WatchlistGroupRestoreRequest'];
type OpenApiListGet200 =
  operations['list_watchlist_groups_api_v1_stocks_watchlist_groups_get']['responses']['200']['content']['application/json'];
type OpenApiCreatePost200 =
  operations['create_watchlist_group_api_v1_stocks_watchlist_groups_post']['responses']['200']['content']['application/json'];
type OpenApiRestorePost200 =
  operations['restore_watchlist_group_api_v1_stocks_watchlist_groups_restore_post']['responses']['200']['content']['application/json'];
type OpenApiCreateBody =
  operations['create_watchlist_group_api_v1_stocks_watchlist_groups_post']['requestBody']['content']['application/json'];
type OpenApiRestoreBody =
  operations['restore_watchlist_group_api_v1_stocks_watchlist_groups_restore_post']['requestBody']['content']['application/json'];
type OpenApiListPathGet = paths['/api/v1/stocks/watchlist/groups']['get'];
type OpenApiCreatePathPost = paths['/api/v1/stocks/watchlist/groups']['post'];
type OpenApiRestorePathPost = paths['/api/v1/stocks/watchlist/groups/restore']['post'];
type OpenApiListOp = operations['list_watchlist_groups_api_v1_stocks_watchlist_groups_get'];
type OpenApiCreateOp = operations['create_watchlist_group_api_v1_stocks_watchlist_groups_post'];
type OpenApiRestoreOp = operations['restore_watchlist_group_api_v1_stocks_watchlist_groups_restore_post'];

type _Assert<T extends true> = T;
type _List200IsResponse = _Assert<OpenApiListGet200 extends OpenApiGroupsResponse ? true : false>;
type _ResponseIsList200 = _Assert<OpenApiGroupsResponse extends OpenApiListGet200 ? true : false>;
type _Create200IsResponse = _Assert<OpenApiCreatePost200 extends OpenApiGroupsResponse ? true : false>;
type _ResponseIsCreate200 = _Assert<OpenApiGroupsResponse extends OpenApiCreatePost200 ? true : false>;
type _Restore200IsResponse = _Assert<OpenApiRestorePost200 extends OpenApiGroupsResponse ? true : false>;
type _ResponseIsRestore200 = _Assert<OpenApiGroupsResponse extends OpenApiRestorePost200 ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreateRequest ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreateRequest extends OpenApiCreateBody ? true : false>;
type _RestoreBodyIsRequest = _Assert<OpenApiRestoreBody extends OpenApiRestoreRequest ? true : false>;
type _RequestIsRestoreBody = _Assert<OpenApiRestoreRequest extends OpenApiRestoreBody ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _ListPathIsOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _CreateOpIsPath = _Assert<OpenApiCreateOp extends OpenApiCreatePathPost ? true : false>;
type _CreatePathIsOp = _Assert<OpenApiCreatePathPost extends OpenApiCreateOp ? true : false>;
type _RestoreOpIsPath = _Assert<OpenApiRestoreOp extends OpenApiRestorePathPost ? true : false>;
type _RestorePathIsOp = _Assert<OpenApiRestorePathPost extends OpenApiRestoreOp ? true : false>;
type _ListOpHasNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _SchemaVersionIsOne = _Assert<OpenApiComputedAttrs['schema_version'] extends 1 ? true : false>;
type _OneIsSchemaVersion = _Assert<1 extends OpenApiComputedAttrs['schema_version'] ? true : false>;

type _OpenApiAnchors = [
  _List200IsResponse,
  _ResponseIsList200,
  _Create200IsResponse,
  _ResponseIsCreate200,
  _Restore200IsResponse,
  _ResponseIsRestore200,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _RestoreBodyIsRequest,
  _RequestIsRestoreBody,
  _ListOpIsPath,
  _ListPathIsOp,
  _CreateOpIsPath,
  _CreatePathIsOp,
  _RestoreOpIsPath,
  _RestorePathIsOp,
  _ListOpHasNeverRequestBody,
  _SchemaVersionIsOne,
  _OneIsSchemaVersion,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export interface HomeWatchlistRow {
  code: string;
  latestItem?: StockBarItem;
  analyzedToday: boolean;
  isTodayStatusLoading?: boolean;
  isTodayStatusUnknown?: boolean;
  activeTask?: TaskInfo;
}

/** Read-only, versioned projection owned by T25/T26 services. */
export type WatchlistMemberAttrs = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiComputedAttrs>, {
  schemaVersion: 1;
  aiScore?: number | null;
  focus?: boolean | null;
}>>;

export type WatchlistGroupMember = Override<CamelizeKeys<OpenApiMember>, {
  stockCode: string;
  sortOrder: number;
  attrs: WatchlistMemberAttrs;
}>;

export type WatchlistGroup = Override<CamelizeKeys<OpenApiGroup>, {
  id: string;
  name: string;
  nameKey?: string | null;
  sortOrder: number;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  members: WatchlistGroupMember[];
}>;

export type WatchlistGroupState = Override<Omit<CamelizeKeys<OpenApiGroupsResponse>, 'message'>, {
  revision: number;
  groups: WatchlistGroup[];
}>;

/** Snapshot required to restore a deleted group through the revisioned API. */
export interface WatchlistGroupRestoreSnapshot {
  groupId: string;
  name: string;
  memberCodes: string[];
  exclusiveMemberCodes: string[];
  orderedGroupIds: string[];
}
