// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Plugins from '../plugins';
import type {
  PluginInfo,
  PluginLifecycleAction,
  PluginLifecycleResponse,
  PluginLifecycleState,
  PluginListResponse,
  PluginSettingField,
  PluginSettingOption,
  PluginSettingValue,
  PluginSettingsResponse,
  PluginSettingsUpdateResponse,
  PluginSource,
} from '../plugins';
import type * as ApiPlugins from '../../api/plugins';

type OpenApiPluginInfo = components['schemas']['PluginInfo'];
type OpenApiPluginListResponse = components['schemas']['PluginListResponse'];
type OpenApiPluginLifecycleResponse = components['schemas']['PluginLifecycleResponse'];
type OpenApiPluginSettingOption = components['schemas']['PluginSettingOptionResponse'];
type OpenApiPluginSettingsResponse = components['schemas']['PluginSettingsResponse'];
type OpenApiPluginSettingsUpdateResponse = components['schemas']['PluginSettingsUpdateResponse'];
type OpenApiListOp = operations['listPlugins'];
type OpenApiLifecycleOp = operations['updatePluginLifecycle'];
type OpenApiGetSettingsOp = operations['getPluginSettings'];
type OpenApiUpdateSettingsOp = operations['updatePluginSettings'];
type OpenApiPathListGet = paths['/api/v1/plugins']['get'];
type OpenApiList200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiLifecycle200 = OpenApiLifecycleOp['responses']['200']['content']['application/json'];
type OpenApiGetSettings200 = OpenApiGetSettingsOp['responses']['200']['content']['application/json'];
type OpenApiUpdateSettings200 =
  OpenApiUpdateSettingsOp['responses']['200']['content']['application/json'];

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

type _NineComponents = _Assert<
  (
    | 'PluginInfo'
    | 'PluginListResponse'
    | 'PluginLifecycleRequest'
    | 'PluginLifecycleResponse'
    | 'PluginSettingOptionResponse'
    | 'PluginSettingFieldResponse'
    | 'PluginSettingsResponse'
    | 'PluginSettingsUpdateRequest'
    | 'PluginSettingsUpdateResponse'
  ) extends keyof components['schemas'] ? true : false
>;
type _HealthExists = _Assert<'PluginHealthResponse' extends keyof components['schemas'] ? true : false>;
type _HealthEntryExists = _Assert<
  'PluginHealthEntryResponse' extends keyof components['schemas'] ? true : false
>;
type _HealthPathExists = _Assert<
  paths['/api/v1/plugins/health']['get'] extends operations['getPluginHealth'] ? true : false
>;
type _HealthNotImported = _Assert<
  'PluginHealthResponse' extends keyof typeof import('../plugins') ? false : true
>;
type _HealthEntryNotImported = _Assert<
  'PluginHealthEntryResponse' extends keyof typeof import('../plugins') ? false : true
>;
type _UpdateRequestNotImported = _Assert<
  'PluginSettingsUpdateRequest' extends keyof typeof import('../plugins') ? false : true
>;
type _LifecycleRequestNotImported = _Assert<
  'PluginLifecycleRequest' extends keyof typeof import('../plugins') ? false : true
>;
type _List200IsComponent = _Assert<OpenApiList200 extends OpenApiPluginListResponse ? true : false>;
type _ComponentIsList200 = _Assert<OpenApiPluginListResponse extends OpenApiList200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiPathListGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiPathListGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _PathListPostNever = _Assert<
  paths['/api/v1/plugins']['post'] extends never | undefined ? true : false
>;
type _PathListPutNever = _Assert<
  paths['/api/v1/plugins']['put'] extends never | undefined ? true : false
>;
type _PathListDeleteNever = _Assert<
  paths['/api/v1/plugins']['delete'] extends never | undefined ? true : false
>;
type _PathListPatchNever = _Assert<
  paths['/api/v1/plugins']['patch'] extends never | undefined ? true : false
>;
type _UiItemsRequired = _Assert<IsOptional<PluginListResponse, 'items'> extends false ? true : false>;
type _GeneratedItemsOptional = _Assert<IsOptional<OpenApiPluginListResponse, 'items'>>;
type _NaiveItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiPluginListResponse>, 'items'>>;
type _UiExtensionPointsRequired = _Assert<
  IsOptional<PluginInfo, 'extensionPoints'> extends false ? true : false
>;
type _UiNotificationChannelsRequired = _Assert<
  IsOptional<PluginInfo, 'notificationChannels'> extends false ? true : false
>;
type _GeneratedExtensionPointsOptional = _Assert<IsOptional<OpenApiPluginInfo, 'extension_points'>>;
type _GeneratedNotificationChannelsOptional = _Assert<
  IsOptional<OpenApiPluginInfo, 'notification_channels'>
>;
type _NaiveExtensionPointsOptional = _Assert<
  IsOptional<CamelizeKeys<OpenApiPluginInfo>, 'extensionPoints'>
>;
type _PackageRootOptional = _Assert<IsOptional<PluginInfo, 'packageRoot'>>;
type _LastErrorCodeOptional = _Assert<IsOptional<PluginInfo, 'lastErrorCode'>>;
type _LifecyclePluginOptional = _Assert<IsOptional<PluginLifecycleResponse, 'plugin'>>;
type _StringStateRejected = _Assert<string extends PluginLifecycleState ? false : true>;
type _StringSourceRejected = _Assert<string extends PluginSource ? false : true>;
type _StateClosed = _Assert<
  PluginLifecycleState extends 'registered' | 'enabled' | 'disabled' | 'failed'
    ? 'registered' | 'enabled' | 'disabled' | 'failed' extends PluginLifecycleState ? true : false
    : false
>;
type _SourceClosed = _Assert<
  PluginSource extends 'builtin' | 'external'
    ? 'builtin' | 'external' extends PluginSource ? true : false
    : false
>;
type _ActionClosed = _Assert<
  PluginLifecycleAction extends 'enable' | 'disable' | 'reload'
    ? 'enable' | 'disable' | 'reload' extends PluginLifecycleAction ? true : false
    : false
>;
type _OptionEqualsFieldOption = _Assert<
  PluginSettingField['options'][number] extends PluginSettingOption
    ? PluginSettingOption extends PluginSettingField['options'][number] ? true : false
    : false
>;
type _OptionEqualsGeneratedCamel = _Assert<
  PluginSettingOption extends CamelizeKeys<OpenApiPluginSettingOption>
    ? CamelizeKeys<OpenApiPluginSettingOption> extends PluginSettingOption ? true : false
    : false
>;
type _PublicInfoNotGenerated = _Assert<
  PluginInfo extends OpenApiPluginInfo ? false : true
>;
type _PublicListNotGenerated = _Assert<
  PluginListResponse extends OpenApiPluginListResponse ? false : true
>;
type _SettingValueFinite = _Assert<
  PluginSettingValue extends string | number | boolean | null
    ? string | number | boolean | null extends PluginSettingValue ? true : false
    : false
>;
type _UnknownValueRejected = _Assert<unknown extends PluginSettingValue ? false : true>;
type _UiHasExtensionPoints = _Assert<'extensionPoints' extends keyof PluginInfo ? true : false>;
type _UiLacksExtensionPointsSnake = _Assert<'extension_points' extends keyof PluginInfo ? false : true>;
type _GeneratedHasExtensionPointsSnake = _Assert<
  'extension_points' extends keyof OpenApiPluginInfo ? true : false
>;
type _GeneratedLacksExtensionPointsCamel = _Assert<
  'extensionPoints' extends keyof OpenApiPluginInfo ? false : true
>;

type _CompileTimePins = [
  _NineComponents, _HealthExists, _HealthEntryExists, _HealthPathExists, _HealthNotImported,
  _HealthEntryNotImported, _UpdateRequestNotImported, _LifecycleRequestNotImported,
  _List200IsComponent, _ComponentIsList200, _ListOpIsPath, _PathIsListOp,
  _ListGetNeverRequestBody, _PathListPostNever, _PathListPutNever, _PathListDeleteNever,
  _PathListPatchNever, _UiItemsRequired, _GeneratedItemsOptional, _NaiveItemsOptional,
  _UiExtensionPointsRequired, _UiNotificationChannelsRequired, _GeneratedExtensionPointsOptional,
  _GeneratedNotificationChannelsOptional, _NaiveExtensionPointsOptional, _PackageRootOptional,
  _LastErrorCodeOptional, _LifecyclePluginOptional, _StringStateRejected, _StringSourceRejected,
  _StateClosed, _SourceClosed, _ActionClosed, _OptionEqualsFieldOption, _OptionEqualsGeneratedCamel,
  _PublicInfoNotGenerated, _PublicListNotGenerated, _SettingValueFinite, _UnknownValueRejected,
  _UiHasExtensionPoints, _UiLacksExtensionPointsSnake, _GeneratedHasExtensionPointsSnake,
  _GeneratedLacksExtensionPointsCamel,
];

describe('plugins OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Plugins }).toEqual({});
    expect(Object.keys(Plugins)).toEqual([]);
    expect(Object.getOwnPropertyNames(Plugins)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('does not equal generated snake_case PluginInfo or PluginListResponse', () => {
    expectTypeOf<PluginInfo>().not.toEqualTypeOf<OpenApiPluginInfo>();
    expectTypeOf<PluginListResponse>().not.toEqualTypeOf<OpenApiPluginListResponse>();
    expectTypeOf<PluginInfo>().not.toEqualTypeOf<CamelizeKeys<OpenApiPluginInfo>>();
    expectTypeOf<PluginListResponse>().not.toEqualTypeOf<CamelizeKeys<OpenApiPluginListResponse>>();
  });

  it('rejects string as PluginLifecycleState and PluginSource', () => {
    expectTypeOf<string>().not.toMatchTypeOf<PluginLifecycleState>();
    expectTypeOf<string>().not.toMatchTypeOf<PluginSource>();
    expectTypeOf<PluginLifecycleState>().toEqualTypeOf<
      'registered' | 'enabled' | 'disabled' | 'failed'
    >();
    expectTypeOf<PluginSource>().toEqualTypeOf<'builtin' | 'external'>();
  });

  it('requires list items and plugin extension arrays that generated leaves optional', () => {
    type UiItemsOptional = IsOptional<PluginListResponse, 'items'>;
    type GeneratedItemsOptional = IsOptional<OpenApiPluginListResponse, 'items'>;
    type UiExtensionOptional = IsOptional<PluginInfo, 'extensionPoints'>;
    type UiChannelsOptional = IsOptional<PluginInfo, 'notificationChannels'>;
    type GeneratedExtensionOptional = IsOptional<OpenApiPluginInfo, 'extension_points'>;
    type GeneratedChannelsOptional = IsOptional<OpenApiPluginInfo, 'notification_channels'>;
    expectTypeOf<UiItemsOptional>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedItemsOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiExtensionOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiChannelsOptional>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedExtensionOptional>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedChannelsOptional>().toEqualTypeOf<true>();
    expectTypeOf<PluginInfo['extensionPoints']>().toEqualTypeOf<string[]>();
    expectTypeOf<PluginInfo['notificationChannels']>().toEqualTypeOf<string[]>();
  });

  it('equates nested setting options to PluginSettingOption', () => {
    expectTypeOf<PluginSettingField['options'][number]>().toEqualTypeOf<PluginSettingOption>();
    expectTypeOf<PluginSettingOption>().toEqualTypeOf<CamelizeKeys<OpenApiPluginSettingOption>>();
  });

  it('keeps GET /api/v1/plugins requestBody never and unused methods never', () => {
    type ListGetNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type ListPostNever = paths['/api/v1/plugins']['post'] extends never | undefined ? true : false;
    type ListPutNever = paths['/api/v1/plugins']['put'] extends never | undefined ? true : false;
    type ListDeleteNever = paths['/api/v1/plugins']['delete'] extends never | undefined ? true : false;
    type ListPatchNever = paths['/api/v1/plugins']['patch'] extends never | undefined ? true : false;
    expectTypeOf<ListGetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ListPostNever>().toEqualTypeOf<true>();
    expectTypeOf<ListPutNever>().toEqualTypeOf<true>();
    expectTypeOf<ListDeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<ListPatchNever>().toEqualTypeOf<true>();
    expectTypeOf<OpenApiList200>().toEqualTypeOf<OpenApiPluginListResponse>();
    expectTypeOf<OpenApiLifecycle200>().toEqualTypeOf<OpenApiPluginLifecycleResponse>();
    expectTypeOf<OpenApiGetSettings200>().toEqualTypeOf<OpenApiPluginSettingsResponse>();
    expectTypeOf<OpenApiUpdateSettings200>().toEqualTypeOf<OpenApiPluginSettingsUpdateResponse>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiPathListGet>();
  });

  it('does not export PluginHealthResponse or PluginSettingsUpdateRequest', () => {
    type HealthKey = 'PluginHealthResponse' extends keyof typeof import('../plugins') ? true : false;
    type UpdateRequestKey =
      'PluginSettingsUpdateRequest' extends keyof typeof import('../plugins') ? true : false;
    expectTypeOf<HealthKey>().toEqualTypeOf<false>();
    expectTypeOf<UpdateRequestKey>().toEqualTypeOf<false>();
    expectTypeOf<operations['getPluginHealth']>().not.toEqualTypeOf<never>();
  });

  it('re-exports the public camelCase names from api/plugins', () => {
    expectTypeOf<ApiPlugins.PluginLifecycleAction>().toEqualTypeOf<PluginLifecycleAction>();
    expectTypeOf<ApiPlugins.PluginLifecycleState>().toEqualTypeOf<PluginLifecycleState>();
    expectTypeOf<ApiPlugins.PluginSource>().toEqualTypeOf<PluginSource>();
    expectTypeOf<ApiPlugins.PluginSettingValue>().toEqualTypeOf<PluginSettingValue>();
    expectTypeOf<ApiPlugins.PluginInfo>().toEqualTypeOf<PluginInfo>();
    expectTypeOf<ApiPlugins.PluginListResponse>().toEqualTypeOf<PluginListResponse>();
    expectTypeOf<ApiPlugins.PluginLifecycleResponse>().toEqualTypeOf<PluginLifecycleResponse>();
    expectTypeOf<ApiPlugins.PluginSettingOption>().toEqualTypeOf<PluginSettingOption>();
    expectTypeOf<ApiPlugins.PluginSettingField>().toEqualTypeOf<PluginSettingField>();
    expectTypeOf<ApiPlugins.PluginSettingsResponse>().toEqualTypeOf<PluginSettingsResponse>();
    expectTypeOf<ApiPlugins.PluginSettingsUpdateResponse>().toEqualTypeOf<
      PluginSettingsUpdateResponse
    >();
  });
});
