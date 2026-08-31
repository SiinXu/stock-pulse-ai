// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Watchlist from '../watchlist';
import type {
  HomeWatchlistRow,
  WatchlistGroup,
  WatchlistGroupMember,
  WatchlistGroupRestoreSnapshot,
  WatchlistGroupState,
  WatchlistMemberAttrs,
} from '../watchlist';

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

type _UiHasStockCode = _Assert<'stockCode' extends keyof WatchlistGroupMember ? true : false>;
type _UiHasSortOrder = _Assert<'sortOrder' extends keyof WatchlistGroupMember ? true : false>;
type _UiHasIsDefault = _Assert<'isDefault' extends keyof WatchlistGroup ? true : false>;
type _UiHasCreatedAt = _Assert<'createdAt' extends keyof WatchlistGroup ? true : false>;
type _UiHasNameKey = _Assert<'nameKey' extends keyof WatchlistGroup ? true : false>;
type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof WatchlistMemberAttrs ? true : false>;
type _UiHasAiScore = _Assert<'aiScore' extends keyof WatchlistMemberAttrs ? true : false>;

type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof WatchlistGroupMember ? false : true>;
type _UiLacksSortOrderSnake = _Assert<'sort_order' extends keyof WatchlistGroupMember ? false : true>;
type _UiLacksIsDefaultSnake = _Assert<'is_default' extends keyof WatchlistGroup ? false : true>;
type _UiLacksCreatedAtSnake = _Assert<'created_at' extends keyof WatchlistGroup ? false : true>;
type _UiLacksNameKeySnake = _Assert<'name_key' extends keyof WatchlistGroup ? false : true>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof WatchlistMemberAttrs ? false : true>;
type _UiLacksAiScoreSnake = _Assert<'ai_score' extends keyof WatchlistMemberAttrs ? false : true>;

type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiMember ? true : false>;
type _GeneratedHasSortOrderSnake = _Assert<'sort_order' extends keyof OpenApiMember ? true : false>;
type _GeneratedHasIsDefaultSnake = _Assert<'is_default' extends keyof OpenApiGroup ? true : false>;
type _GeneratedHasCreatedAtSnake = _Assert<'created_at' extends keyof OpenApiGroup ? true : false>;
type _GeneratedHasNameKeySnake = _Assert<'name_key' extends keyof OpenApiGroup ? true : false>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiComputedAttrs ? true : false>;
type _GeneratedHasAiScoreSnake = _Assert<'ai_score' extends keyof OpenApiComputedAttrs ? true : false>;

type _UiLacksStockCodeCamelOnGenerated = _Assert<'stockCode' extends keyof OpenApiMember ? false : true>;
type _UiLacksSchemaVersionCamelOnGenerated = _Assert<'schemaVersion' extends keyof OpenApiComputedAttrs ? false : true>;
type _UiLacksIsDefaultCamelOnGenerated = _Assert<'isDefault' extends keyof OpenApiGroup ? false : true>;

type _UiGroupsRequired = _Assert<IsOptional<WatchlistGroupState, 'groups'> extends false ? true : false>;
type _GeneratedGroupsOptional = _Assert<IsOptional<OpenApiGroupsResponse, 'groups'>>;
type _UiMembersRequired = _Assert<IsOptional<WatchlistGroup, 'members'> extends false ? true : false>;
type _GeneratedMembersOptional = _Assert<IsOptional<OpenApiGroup, 'members'>>;
type _UiAttrsRequired = _Assert<IsOptional<WatchlistGroupMember, 'attrs'> extends false ? true : false>;
type _GeneratedAttrsOptional = _Assert<IsOptional<OpenApiMember, 'attrs'>>;
type _UiSchemaVersionRequired = _Assert<
  IsOptional<WatchlistMemberAttrs, 'schemaVersion'> extends false ? true : false
>;
type _GeneratedSchemaVersionRequired = _Assert<
  IsOptional<OpenApiComputedAttrs, 'schema_version'> extends false ? true : false
>;
type _UiSchemaVersionLiteral = _Assert<WatchlistMemberAttrs['schemaVersion'] extends 1 ? true : false>;
type _OneIsUiSchemaVersion = _Assert<1 extends WatchlistMemberAttrs['schemaVersion'] ? true : false>;

type _UiStateLacksMessage = _Assert<'message' extends keyof WatchlistGroupState ? false : true>;
type _GeneratedHasMessage = _Assert<'message' extends keyof OpenApiGroupsResponse ? true : false>;
type _GeneratedMessageRequired = _Assert<
  IsOptional<OpenApiGroupsResponse, 'message'> extends false ? true : false
>;

type _OmitGroups = _Assert<Omit<WatchlistGroupState, 'groups'> extends WatchlistGroupState ? false : true>;
type _OmitGeneratedGroups = _Assert<Omit<OpenApiGroupsResponse, 'groups'> extends OpenApiGroupsResponse ? true : false>;
type _OmitMembers = _Assert<Omit<WatchlistGroup, 'members'> extends WatchlistGroup ? false : true>;
type _OmitGeneratedMembers = _Assert<Omit<OpenApiGroup, 'members'> extends OpenApiGroup ? true : false>;
type _OmitAttrs = _Assert<Omit<WatchlistGroupMember, 'attrs'> extends WatchlistGroupMember ? false : true>;
type _OmitGeneratedAttrs = _Assert<Omit<OpenApiMember, 'attrs'> extends OpenApiMember ? true : false>;

type _HomeHasCode = _Assert<'code' extends keyof HomeWatchlistRow ? true : false>;
type _HomeHasAnalyzedToday = _Assert<'analyzedToday' extends keyof HomeWatchlistRow ? true : false>;
type _HomeIsNotGeneratedGroup = _Assert<HomeWatchlistRow extends OpenApiGroup ? false : true>;
type _HomeIsNotGeneratedResponse = _Assert<HomeWatchlistRow extends OpenApiGroupsResponse ? false : true>;
type _GeneratedGroupIsNotHome = _Assert<OpenApiGroup extends HomeWatchlistRow ? false : true>;
type _GeneratedResponseIsNotHome = _Assert<OpenApiGroupsResponse extends HomeWatchlistRow ? false : true>;

type _UiRestoreHasExclusiveMemberCodes = _Assert<
  'exclusiveMemberCodes' extends keyof WatchlistGroupRestoreSnapshot ? true : false
>;
type _UiRestoreHasOrderedGroupIds = _Assert<
  'orderedGroupIds' extends keyof WatchlistGroupRestoreSnapshot ? true : false
>;
type _UiRestoreLacksExclusiveCodes = _Assert<
  'exclusiveCodes' extends keyof WatchlistGroupRestoreSnapshot ? false : true
>;
type _UiRestoreLacksOrderedIds = _Assert<'orderedIds' extends keyof WatchlistGroupRestoreSnapshot ? false : true>;
type _UiRestoreLacksExclusiveCodesSnake = _Assert<
  'exclusive_codes' extends keyof WatchlistGroupRestoreSnapshot ? false : true
>;
type _UiRestoreLacksOrderedIdsSnake = _Assert<
  'ordered_ids' extends keyof WatchlistGroupRestoreSnapshot ? false : true
>;
type _GeneratedRestoreHasExclusiveCodesSnake = _Assert<
  'exclusive_codes' extends keyof OpenApiRestoreRequest ? true : false
>;
type _GeneratedRestoreHasOrderedIdsSnake = _Assert<'ordered_ids' extends keyof OpenApiRestoreRequest ? true : false>;
type _NaiveCamelHasExclusiveCodes = _Assert<
  'exclusiveCodes' extends keyof CamelizeKeys<OpenApiRestoreRequest> ? true : false
>;
type _NaiveCamelHasOrderedIds = _Assert<'orderedIds' extends keyof CamelizeKeys<OpenApiRestoreRequest> ? true : false>;
type _NaiveCamelLacksExclusiveMemberCodes = _Assert<
  'exclusiveMemberCodes' extends keyof CamelizeKeys<OpenApiRestoreRequest> ? false : true
>;
type _NaiveCamelLacksOrderedGroupIds = _Assert<
  'orderedGroupIds' extends keyof CamelizeKeys<OpenApiRestoreRequest> ? false : true
>;

type NarrowAttrs = {
  schemaVersion: 1;
};
type NarrowMember = {
  stockCode: string;
  sortOrder: number;
  attrs: NarrowAttrs;
};
type NarrowGroup = {
  id: string;
  name: string;
  sortOrder: number;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  members: NarrowMember[];
};
type NarrowState = {
  revision: number;
  groups: NarrowGroup[];
};
type NarrowHome = {
  code: string;
  analyzedToday: boolean;
};
type NarrowRestore = {
  groupId: string;
  name: string;
  memberCodes: string[];
  exclusiveMemberCodes: string[];
  orderedGroupIds: string[];
};

type _NarrowAttrsAssignable = _Assert<NarrowAttrs extends WatchlistMemberAttrs ? true : false>;
type _NarrowMemberAssignable = _Assert<NarrowMember extends WatchlistGroupMember ? true : false>;
type _NarrowGroupAssignable = _Assert<NarrowGroup extends WatchlistGroup ? true : false>;
type _NarrowStateAssignable = _Assert<NarrowState extends WatchlistGroupState ? true : false>;
type _NarrowHomeAssignable = _Assert<NarrowHome extends HomeWatchlistRow ? true : false>;
type _NarrowRestoreAssignable = _Assert<NarrowRestore extends WatchlistGroupRestoreSnapshot ? true : false>;

type SnakeMember = {
  stock_code: string;
  sort_order: number;
};
type SnakeGroup = {
  created_at: string;
  id: string;
  is_default: boolean;
  name: string;
  sort_order: number;
  updated_at: string;
};
type SnakeResponse = {
  message: string;
  revision: number;
};
type SnakeRestore = {
  expected_revision: number;
  group_id: string;
  name: string;
  exclusive_codes: string[];
  ordered_ids: string[];
};
type NaiveCamelRestore = {
  expectedRevision: number;
  groupId: string;
  name: string;
  exclusiveCodes: string[];
  orderedIds: string[];
};

type _SnakeMemberMatchesGenerated = _Assert<SnakeMember extends OpenApiMember ? true : false>;
type _SnakeMemberDoesNotMatchUi = _Assert<SnakeMember extends WatchlistGroupMember ? false : true>;
type _SnakeGroupMatchesGenerated = _Assert<SnakeGroup extends OpenApiGroup ? true : false>;
type _SnakeGroupDoesNotMatchUi = _Assert<SnakeGroup extends WatchlistGroup ? false : true>;
type _SnakeResponseMatchesGenerated = _Assert<SnakeResponse extends OpenApiGroupsResponse ? true : false>;
type _SnakeResponseDoesNotMatchUi = _Assert<SnakeResponse extends WatchlistGroupState ? false : true>;
type _SnakeRestoreMatchesGenerated = _Assert<SnakeRestore extends OpenApiRestoreRequest ? true : false>;
type _SnakeRestoreDoesNotMatchUi = _Assert<SnakeRestore extends WatchlistGroupRestoreSnapshot ? false : true>;
type _NaiveCamelRestoreMatchesGeneratedCamel = _Assert<
  NaiveCamelRestore extends CamelizeKeys<OpenApiRestoreRequest> ? true : false
>;
type _NaiveCamelRestoreDoesNotMatchUi = _Assert<
  NaiveCamelRestore extends WatchlistGroupRestoreSnapshot ? false : true
>;
type _UiStateIsNotGeneratedAlias = _Assert<WatchlistGroupState extends OpenApiGroupsResponse ? false : true>;
type _GeneratedResponseIsNotUi = _Assert<OpenApiGroupsResponse extends WatchlistGroupState ? false : true>;
type _UiStateKeysOnlyRevisionAndGroups = _Assert<
  keyof WatchlistGroupState extends 'revision' | 'groups' ? true : false
>;
type _UiStateHasRevisionAndGroups = _Assert<
  'revision' | 'groups' extends keyof WatchlistGroupState ? true : false
>;

type _CompileTimePins = [
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
  _UiHasStockCode,
  _UiHasSortOrder,
  _UiHasIsDefault,
  _UiHasCreatedAt,
  _UiHasNameKey,
  _UiHasSchemaVersion,
  _UiHasAiScore,
  _UiLacksStockCodeSnake,
  _UiLacksSortOrderSnake,
  _UiLacksIsDefaultSnake,
  _UiLacksCreatedAtSnake,
  _UiLacksNameKeySnake,
  _UiLacksSchemaVersionSnake,
  _UiLacksAiScoreSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasSortOrderSnake,
  _GeneratedHasIsDefaultSnake,
  _GeneratedHasCreatedAtSnake,
  _GeneratedHasNameKeySnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasAiScoreSnake,
  _UiLacksStockCodeCamelOnGenerated,
  _UiLacksSchemaVersionCamelOnGenerated,
  _UiLacksIsDefaultCamelOnGenerated,
  _UiGroupsRequired,
  _GeneratedGroupsOptional,
  _UiMembersRequired,
  _GeneratedMembersOptional,
  _UiAttrsRequired,
  _GeneratedAttrsOptional,
  _UiSchemaVersionRequired,
  _GeneratedSchemaVersionRequired,
  _UiSchemaVersionLiteral,
  _OneIsUiSchemaVersion,
  _UiStateLacksMessage,
  _GeneratedHasMessage,
  _GeneratedMessageRequired,
  _OmitGroups,
  _OmitGeneratedGroups,
  _OmitMembers,
  _OmitGeneratedMembers,
  _OmitAttrs,
  _OmitGeneratedAttrs,
  _HomeHasCode,
  _HomeHasAnalyzedToday,
  _HomeIsNotGeneratedGroup,
  _HomeIsNotGeneratedResponse,
  _GeneratedGroupIsNotHome,
  _GeneratedResponseIsNotHome,
  _UiRestoreHasExclusiveMemberCodes,
  _UiRestoreHasOrderedGroupIds,
  _UiRestoreLacksExclusiveCodes,
  _UiRestoreLacksOrderedIds,
  _UiRestoreLacksExclusiveCodesSnake,
  _UiRestoreLacksOrderedIdsSnake,
  _GeneratedRestoreHasExclusiveCodesSnake,
  _GeneratedRestoreHasOrderedIdsSnake,
  _NaiveCamelHasExclusiveCodes,
  _NaiveCamelHasOrderedIds,
  _NaiveCamelLacksExclusiveMemberCodes,
  _NaiveCamelLacksOrderedGroupIds,
  _NarrowAttrsAssignable,
  _NarrowMemberAssignable,
  _NarrowGroupAssignable,
  _NarrowStateAssignable,
  _NarrowHomeAssignable,
  _NarrowRestoreAssignable,
  _SnakeMemberMatchesGenerated,
  _SnakeMemberDoesNotMatchUi,
  _SnakeGroupMatchesGenerated,
  _SnakeGroupDoesNotMatchUi,
  _SnakeResponseMatchesGenerated,
  _SnakeResponseDoesNotMatchUi,
  _SnakeRestoreMatchesGenerated,
  _SnakeRestoreDoesNotMatchUi,
  _NaiveCamelRestoreMatchesGeneratedCamel,
  _NaiveCamelRestoreDoesNotMatchUi,
  _UiStateIsNotGeneratedAlias,
  _GeneratedResponseIsNotUi,
  _UiStateKeysOnlyRevisionAndGroups,
  _UiStateHasRevisionAndGroups,
];

describe('watchlist OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Watchlist }).toEqual({});
    expect(Object.keys(Watchlist)).toEqual([]);
    expect(Object.getOwnPropertyNames(Watchlist)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON and request bodies to the generated components', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiGroupsResponse>();
    expectTypeOf<OpenApiCreatePost200>().toEqualTypeOf<OpenApiGroupsResponse>();
    expectTypeOf<OpenApiRestorePost200>().toEqualTypeOf<OpenApiGroupsResponse>();
    expectTypeOf<OpenApiCreateBody>().toEqualTypeOf<OpenApiCreateRequest>();
    expectTypeOf<OpenApiRestoreBody>().toEqualTypeOf<OpenApiRestoreRequest>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiCreateOp>().toEqualTypeOf<OpenApiCreatePathPost>();
    expectTypeOf<OpenApiRestoreOp>().toEqualTypeOf<OpenApiRestorePathPost>();
    type ListRequestBodyNever = OpenApiListOp extends { requestBody?: never } ? true : false;
    expectTypeOf<ListRequestBodyNever>().toEqualTypeOf<true>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof WatchlistGroupMember>().not.toMatchTypeOf<'stock_code' | 'sort_order'>();
    expectTypeOf<keyof WatchlistGroup>().not.toMatchTypeOf<
      'is_default' | 'created_at' | 'updated_at' | 'name_key' | 'sort_order'
    >();
    expectTypeOf<keyof WatchlistMemberAttrs>().not.toMatchTypeOf<'schema_version' | 'ai_score'>();

    type UiHasStockCode = 'stockCode' extends keyof WatchlistGroupMember ? true : false;
    type UiHasStockCodeSnake = 'stock_code' extends keyof WatchlistGroupMember ? true : false;
    type GeneratedHasStockCodeSnake = 'stock_code' extends keyof OpenApiMember ? true : false;
    type UiHasSchemaVersion = 'schemaVersion' extends keyof WatchlistMemberAttrs ? true : false;
    type UiHasSchemaVersionSnake = 'schema_version' extends keyof WatchlistMemberAttrs ? true : false;
    type GeneratedHasSchemaVersionSnake = 'schema_version' extends keyof OpenApiComputedAttrs ? true : false;
    type UiHasIsDefault = 'isDefault' extends keyof WatchlistGroup ? true : false;
    type UiHasIsDefaultSnake = 'is_default' extends keyof WatchlistGroup ? true : false;
    type GeneratedHasIsDefaultSnake = 'is_default' extends keyof OpenApiGroup ? true : false;

    expectTypeOf<UiHasStockCode>().toEqualTypeOf<true>();
    expectTypeOf<UiHasStockCodeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasStockCodeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSchemaVersion>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSchemaVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSchemaVersionSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasIsDefault>().toEqualTypeOf<true>();
    expectTypeOf<UiHasIsDefaultSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasIsDefaultSnake>().toEqualTypeOf<true>();
  });

  it('keeps UI groups, members, and attrs required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<WatchlistGroupState, 'groups'>>().not.toMatchTypeOf<WatchlistGroupState>();
    expectTypeOf<Omit<OpenApiGroupsResponse, 'groups'>>().toMatchTypeOf<OpenApiGroupsResponse>();
    expectTypeOf<Omit<WatchlistGroup, 'members'>>().not.toMatchTypeOf<WatchlistGroup>();
    expectTypeOf<Omit<OpenApiGroup, 'members'>>().toMatchTypeOf<OpenApiGroup>();
    expectTypeOf<Omit<WatchlistGroupMember, 'attrs'>>().not.toMatchTypeOf<WatchlistGroupMember>();
    expectTypeOf<Omit<OpenApiMember, 'attrs'>>().toMatchTypeOf<OpenApiMember>();
  });

  it('omits message from UI state while the generated response keeps it', () => {
    type UiHasMessage = 'message' extends keyof WatchlistGroupState ? true : false;
    type GeneratedHasMessage = 'message' extends keyof OpenApiGroupsResponse ? true : false;
    expectTypeOf<UiHasMessage>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasMessage>().toEqualTypeOf<true>();
    expectTypeOf<keyof WatchlistGroupState>().toEqualTypeOf<'revision' | 'groups'>();
    expectTypeOf<keyof OpenApiGroupsResponse>().toEqualTypeOf<'groups' | 'message' | 'revision'>();
    expectTypeOf({
      revision: 1,
      message: 'ok',
    }).toMatchTypeOf<OpenApiGroupsResponse>();
  });

  it('keeps HomeWatchlistRow a local UI projection', () => {
    type HomeHasCode = 'code' extends keyof HomeWatchlistRow ? true : false;
    type HomeHasAnalyzedToday = 'analyzedToday' extends keyof HomeWatchlistRow ? true : false;
    expectTypeOf<HomeHasCode>().toEqualTypeOf<true>();
    expectTypeOf<HomeHasAnalyzedToday>().toEqualTypeOf<true>();
    const home: HomeWatchlistRow = { code: 'AAPL', analyzedToday: false };
    expectTypeOf(home).toMatchTypeOf<HomeWatchlistRow>();
    expectTypeOf(home).not.toMatchTypeOf<OpenApiGroup>();
    expectTypeOf(home).not.toMatchTypeOf<OpenApiGroupsResponse>();
    expectTypeOf<OpenApiGroup>().not.toMatchTypeOf<HomeWatchlistRow>();
  });

  it('keeps the restore snapshot on exclusiveMemberCodes / orderedGroupIds', () => {
    type UiHasExclusiveMemberCodes = 'exclusiveMemberCodes' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    type UiHasOrderedGroupIds = 'orderedGroupIds' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    type UiHasExclusiveCodes = 'exclusiveCodes' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    type UiHasOrderedIds = 'orderedIds' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    type UiHasExclusiveCodesSnake = 'exclusive_codes' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    type UiHasOrderedIdsSnake = 'ordered_ids' extends keyof WatchlistGroupRestoreSnapshot ? true : false;
    expectTypeOf<UiHasExclusiveMemberCodes>().toEqualTypeOf<true>();
    expectTypeOf<UiHasOrderedGroupIds>().toEqualTypeOf<true>();
    expectTypeOf<UiHasExclusiveCodes>().toEqualTypeOf<false>();
    expectTypeOf<UiHasOrderedIds>().toEqualTypeOf<false>();
    expectTypeOf<UiHasExclusiveCodesSnake>().toEqualTypeOf<false>();
    expectTypeOf<UiHasOrderedIdsSnake>().toEqualTypeOf<false>();

    const snapshot: WatchlistGroupRestoreSnapshot = {
      groupId: 'g1',
      name: 'Default',
      memberCodes: ['AAPL'],
      exclusiveMemberCodes: ['AAPL'],
      orderedGroupIds: ['g1'],
    };
    const snakeRestore = {
      expected_revision: 1,
      group_id: 'g1',
      name: 'Default',
      exclusive_codes: ['AAPL'],
      ordered_ids: ['g1'],
    };
    const naiveCamelRestore = {
      expectedRevision: 1,
      groupId: 'g1',
      name: 'Default',
      exclusiveCodes: ['AAPL'],
      orderedIds: ['g1'],
    };
    expectTypeOf(snapshot).toMatchTypeOf<WatchlistGroupRestoreSnapshot>();
    expectTypeOf(snakeRestore).toMatchTypeOf<OpenApiRestoreRequest>();
    expectTypeOf(snakeRestore).not.toMatchTypeOf<WatchlistGroupRestoreSnapshot>();
    expectTypeOf(naiveCamelRestore).toMatchTypeOf<CamelizeKeys<OpenApiRestoreRequest>>();
    expectTypeOf(naiveCamelRestore).not.toMatchTypeOf<WatchlistGroupRestoreSnapshot>();
  });

  it('still accepts the narrow existing group, member, and state fixtures', () => {
    const attrs: WatchlistMemberAttrs = { schemaVersion: 1, aiScore: 80, focus: true };
    const member: WatchlistGroupMember = {
      stockCode: 'AAPL',
      sortOrder: 0,
      attrs,
    };
    const group: WatchlistGroup = {
      id: 'g1',
      name: 'Default',
      nameKey: null,
      sortOrder: 0,
      isDefault: true,
      createdAt: '2026-08-08T09:00:00+00:00',
      updatedAt: '2026-08-08T09:00:00+00:00',
      members: [member],
    };
    const state: WatchlistGroupState = {
      revision: 1,
      groups: [group],
    };
    expectTypeOf(attrs).toMatchTypeOf<WatchlistMemberAttrs>();
    expectTypeOf(member).toMatchTypeOf<WatchlistGroupMember>();
    expectTypeOf(group).toMatchTypeOf<WatchlistGroup>();
    expectTypeOf(state).toMatchTypeOf<WatchlistGroupState>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeMember = {
      stock_code: 'AAPL',
      sort_order: 0,
    };
    const snakeResponse = {
      revision: 1,
      message: 'ok',
    };
    expectTypeOf(snakeMember).toMatchTypeOf<OpenApiMember>();
    expectTypeOf(snakeMember).not.toMatchTypeOf<WatchlistGroupMember>();
    expectTypeOf(snakeResponse).toMatchTypeOf<OpenApiGroupsResponse>();
    expectTypeOf(snakeResponse).not.toMatchTypeOf<WatchlistGroupState>();
  });
});
