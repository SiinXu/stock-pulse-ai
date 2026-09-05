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

type OpenApiPluginInfo = components['schemas']['PluginInfo'];
type OpenApiPluginListResponse = components['schemas']['PluginListResponse'];
type OpenApiPluginLifecycleRequest = components['schemas']['PluginLifecycleRequest'];
type OpenApiPluginLifecycleResponse = components['schemas']['PluginLifecycleResponse'];
type OpenApiPluginSettingOption = components['schemas']['PluginSettingOptionResponse'];
type OpenApiPluginSettingField = components['schemas']['PluginSettingFieldResponse'];
type OpenApiPluginSettingsResponse = components['schemas']['PluginSettingsResponse'];
type OpenApiPluginSettingsUpdateRequest = components['schemas']['PluginSettingsUpdateRequest'];
type OpenApiPluginSettingsUpdateResponse = components['schemas']['PluginSettingsUpdateResponse'];

type OpenApiListOp = operations['listPlugins'];
type OpenApiLifecycleOp = operations['updatePluginLifecycle'];
type OpenApiGetSettingsOp = operations['getPluginSettings'];
type OpenApiUpdateSettingsOp = operations['updatePluginSettings'];
type OpenApiPathListGet = paths['/api/v1/plugins']['get'];
type OpenApiPathLifecyclePost = paths['/api/v1/plugins/{plugin_id}/lifecycle']['post'];
type OpenApiPathSettingsGet = paths['/api/v1/plugins/{plugin_id}/settings']['get'];
type OpenApiPathSettingsPut = paths['/api/v1/plugins/{plugin_id}/settings']['put'];
type OpenApiList200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiLifecycle200 = OpenApiLifecycleOp['responses']['200']['content']['application/json'];
type OpenApiGetSettings200 = OpenApiGetSettingsOp['responses']['200']['content']['application/json'];
type OpenApiUpdateSettings200 =
  OpenApiUpdateSettingsOp['responses']['200']['content']['application/json'];
type OpenApiLifecycleBody = OpenApiLifecycleOp['requestBody']['content']['application/json'];
type OpenApiUpdateSettingsBody =
  OpenApiUpdateSettingsOp['requestBody']['content']['application/json'];

type _Assert<T extends true> = T;
type _List200IsComponent = _Assert<OpenApiList200 extends OpenApiPluginListResponse ? true : false>;
type _ComponentIsList200 = _Assert<OpenApiPluginListResponse extends OpenApiList200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiPathListGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiPathListGet extends OpenApiListOp ? true : false>;
type _Lifecycle200IsComponent = _Assert<
  OpenApiLifecycle200 extends OpenApiPluginLifecycleResponse ? true : false
>;
type _ComponentIsLifecycle200 = _Assert<
  OpenApiPluginLifecycleResponse extends OpenApiLifecycle200 ? true : false
>;
type _LifecycleOpIsPath = _Assert<OpenApiLifecycleOp extends OpenApiPathLifecyclePost ? true : false>;
type _PathIsLifecycleOp = _Assert<OpenApiPathLifecyclePost extends OpenApiLifecycleOp ? true : false>;
type _LifecycleBodyIsRequest = _Assert<
  OpenApiLifecycleBody extends OpenApiPluginLifecycleRequest ? true : false
>;
type _RequestIsLifecycleBody = _Assert<
  OpenApiPluginLifecycleRequest extends OpenApiLifecycleBody ? true : false
>;
type _GetSettings200IsComponent = _Assert<
  OpenApiGetSettings200 extends OpenApiPluginSettingsResponse ? true : false
>;
type _ComponentIsGetSettings200 = _Assert<
  OpenApiPluginSettingsResponse extends OpenApiGetSettings200 ? true : false
>;
type _GetSettingsOpIsPath = _Assert<OpenApiGetSettingsOp extends OpenApiPathSettingsGet ? true : false>;
type _PathIsGetSettingsOp = _Assert<OpenApiPathSettingsGet extends OpenApiGetSettingsOp ? true : false>;
type _UpdateSettings200IsComponent = _Assert<
  OpenApiUpdateSettings200 extends OpenApiPluginSettingsUpdateResponse ? true : false
>;
type _ComponentIsUpdateSettings200 = _Assert<
  OpenApiPluginSettingsUpdateResponse extends OpenApiUpdateSettings200 ? true : false
>;
type _UpdateSettingsOpIsPath = _Assert<
  OpenApiUpdateSettingsOp extends OpenApiPathSettingsPut ? true : false
>;
type _PathIsUpdateSettingsOp = _Assert<
  OpenApiPathSettingsPut extends OpenApiUpdateSettingsOp ? true : false
>;
type _UpdateSettingsBodyIsRequest = _Assert<
  OpenApiUpdateSettingsBody extends OpenApiPluginSettingsUpdateRequest ? true : false
>;
type _RequestIsUpdateSettingsBody = _Assert<
  OpenApiPluginSettingsUpdateRequest extends OpenApiUpdateSettingsBody ? true : false
>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _GetSettingsNeverRequestBody = _Assert<
  OpenApiGetSettingsOp extends { requestBody?: never } ? true : false
>;
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
type _ListQueryNever = _Assert<
  OpenApiListOp['parameters']['query'] extends never | undefined ? true : false
>;
type _ListHeaderNever = _Assert<
  OpenApiListOp['parameters']['header'] extends never | undefined ? true : false
>;
type _ListPathNever = _Assert<
  OpenApiListOp['parameters']['path'] extends never | undefined ? true : false
>;
type _ListCookieNever = _Assert<
  OpenApiListOp['parameters']['cookie'] extends never | undefined ? true : false
>;
type _LifecyclePathPluginIdIsString = _Assert<
  OpenApiLifecycleOp['parameters']['path']['plugin_id'] extends string
    ? string extends OpenApiLifecycleOp['parameters']['path']['plugin_id'] ? true : false
    : false
>;

type _OpenApiAnchors = [
  _List200IsComponent,
  _ComponentIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _Lifecycle200IsComponent,
  _ComponentIsLifecycle200,
  _LifecycleOpIsPath,
  _PathIsLifecycleOp,
  _LifecycleBodyIsRequest,
  _RequestIsLifecycleBody,
  _GetSettings200IsComponent,
  _ComponentIsGetSettings200,
  _GetSettingsOpIsPath,
  _PathIsGetSettingsOp,
  _UpdateSettings200IsComponent,
  _ComponentIsUpdateSettings200,
  _UpdateSettingsOpIsPath,
  _PathIsUpdateSettingsOp,
  _UpdateSettingsBodyIsRequest,
  _RequestIsUpdateSettingsBody,
  _ListGetNeverRequestBody,
  _GetSettingsNeverRequestBody,
  _PathListPostNever,
  _PathListPutNever,
  _PathListDeleteNever,
  _PathListPatchNever,
  _ListQueryNever,
  _ListHeaderNever,
  _ListPathNever,
  _ListCookieNever,
  _LifecyclePathPluginIdIsString,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type PluginLifecycleAction = OpenApiPluginLifecycleRequest['action'];
export type PluginLifecycleState = OpenApiPluginInfo['state'];
export type PluginSource = OpenApiPluginInfo['source'];
export type PluginSettingValue = string | number | boolean | null;

export type PluginSettingOption = CamelizeKeys<OpenApiPluginSettingOption>;

export type PluginSettingField = Override<CamelizeKeys<OpenApiPluginSettingField>, {
  defaultValue: PluginSettingValue;
  options: PluginSettingOption[];
  validation: Record<string, unknown>;
}>;

export type PluginInfo = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiPluginInfo>, {
  extensionPoints: string[];
  notificationChannels: string[];
}>>;

export type PluginListResponse = Override<CamelizeKeys<OpenApiPluginListResponse>, {
  items: PluginInfo[];
}>;

export type PluginLifecycleResponse = Override<CamelizeKeys<OpenApiPluginLifecycleResponse>, {
  plugin?: PluginInfo | null;
}>;

export type PluginSettingsResponse = Override<CamelizeKeys<OpenApiPluginSettingsResponse>, {
  schema: PluginSettingField[];
  values: Record<string, PluginSettingValue>;
  maskedKeys: string[];
}>;

export type PluginSettingsUpdateResponse = Override<CamelizeKeys<OpenApiPluginSettingsUpdateResponse>, {
  schema: PluginSettingField[];
  values: Record<string, PluginSettingValue>;
  maskedKeys: string[];
  changedKeys: string[];
}>;
