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

type OpenApiChange = components['schemas']['ConfigProfileChange'];
type OpenApiDetection = components['schemas']['ConfigProfileDetection'];
type OpenApiItem = components['schemas']['ConfigPresetItem'];
type OpenApiList = components['schemas']['ConfigPresetListResponse'];
type OpenApiPreview = components['schemas']['ConfigPresetPreviewResponse'];
type OpenApiApply = components['schemas']['ConfigPresetApplyResponse'];
type OpenApiExport = components['schemas']['ConfigProfileExportResponse'];
type OpenApiImportPreview = components['schemas']['ConfigProfileImportPreviewResponse'];
type OpenApiImportApply = components['schemas']['ConfigProfileImportApplyResponse'];
type OpenApiApplyRequest = components['schemas']['ConfigPresetApplyRequest'];
type OpenApiImportRequest = components['schemas']['ConfigProfileImportRequest'];
type OpenApiListGet200 =
  operations['list_config_presets_api_v1_config_profiles_presets_get']['responses']['200']['content']['application/json'];
type OpenApiPreviewPost200 =
  operations['preview_config_preset_api_v1_config_profiles_presets__preset_id__preview_post']['responses']['200']['content']['application/json'];
type OpenApiApplyPost200 =
  operations['apply_config_preset_api_v1_config_profiles_presets__preset_id__apply_post']['responses']['200']['content']['application/json'];
type OpenApiExportGet200 =
  operations['export_config_profile_api_v1_config_profiles_export_get']['responses']['200']['content']['application/json'];
type OpenApiImportPreviewPost200 =
  operations['preview_config_profile_import_api_v1_config_profiles_import_preview_post']['responses']['200']['content']['application/json'];
type OpenApiImportApplyPost200 =
  operations['apply_config_profile_import_api_v1_config_profiles_import_apply_post']['responses']['200']['content']['application/json'];
type OpenApiPreviewBody =
  operations['preview_config_preset_api_v1_config_profiles_presets__preset_id__preview_post']['requestBody']['content']['application/json'];
type OpenApiApplyBody =
  operations['apply_config_preset_api_v1_config_profiles_presets__preset_id__apply_post']['requestBody']['content']['application/json'];
type OpenApiImportPreviewBody =
  operations['preview_config_profile_import_api_v1_config_profiles_import_preview_post']['requestBody']['content']['application/json'];
type OpenApiImportApplyBody =
  operations['apply_config_profile_import_api_v1_config_profiles_import_apply_post']['requestBody']['content']['application/json'];
type OpenApiListPathGet = paths['/api/v1/config-profiles/presets']['get'];
type OpenApiPreviewPathPost = paths['/api/v1/config-profiles/presets/{preset_id}/preview']['post'];
type OpenApiApplyPathPost = paths['/api/v1/config-profiles/presets/{preset_id}/apply']['post'];
type OpenApiExportPathGet = paths['/api/v1/config-profiles/export']['get'];
type OpenApiImportPreviewPathPost = paths['/api/v1/config-profiles/import/preview']['post'];
type OpenApiImportApplyPathPost = paths['/api/v1/config-profiles/import/apply']['post'];
type OpenApiListOp = operations['list_config_presets_api_v1_config_profiles_presets_get'];
type OpenApiPreviewOp = operations['preview_config_preset_api_v1_config_profiles_presets__preset_id__preview_post'];
type OpenApiApplyOp = operations['apply_config_preset_api_v1_config_profiles_presets__preset_id__apply_post'];
type OpenApiExportOp = operations['export_config_profile_api_v1_config_profiles_export_get'];
type OpenApiImportPreviewOp = operations['preview_config_profile_import_api_v1_config_profiles_import_preview_post'];
type OpenApiImportApplyOp = operations['apply_config_profile_import_api_v1_config_profiles_import_apply_post'];

type _Assert<T extends true> = T;
type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiList ? true : false>;
type _ListIsList200 = _Assert<OpenApiList extends OpenApiListGet200 ? true : false>;
type _Preview200IsPreview = _Assert<OpenApiPreviewPost200 extends OpenApiPreview ? true : false>;
type _PreviewIsPreview200 = _Assert<OpenApiPreview extends OpenApiPreviewPost200 ? true : false>;
type _Apply200IsApply = _Assert<OpenApiApplyPost200 extends OpenApiApply ? true : false>;
type _ApplyIsApply200 = _Assert<OpenApiApply extends OpenApiApplyPost200 ? true : false>;
type _Export200IsExport = _Assert<OpenApiExportGet200 extends OpenApiExport ? true : false>;
type _ExportIsExport200 = _Assert<OpenApiExport extends OpenApiExportGet200 ? true : false>;
type _ImportPreview200IsImportPreview = _Assert<
  OpenApiImportPreviewPost200 extends OpenApiImportPreview ? true : false
>;
type _ImportPreviewIsImportPreview200 = _Assert<
  OpenApiImportPreview extends OpenApiImportPreviewPost200 ? true : false
>;
type _ImportApply200IsImportApply = _Assert<OpenApiImportApplyPost200 extends OpenApiImportApply ? true : false>;
type _ImportApplyIsImportApply200 = _Assert<OpenApiImportApply extends OpenApiImportApplyPost200 ? true : false>;
type _PreviewBodyIsApplyRequest = _Assert<OpenApiPreviewBody extends OpenApiApplyRequest ? true : false>;
type _ApplyRequestIsPreviewBody = _Assert<OpenApiApplyRequest extends OpenApiPreviewBody ? true : false>;
type _ApplyBodyIsApplyRequest = _Assert<OpenApiApplyBody extends OpenApiApplyRequest ? true : false>;
type _ApplyRequestIsApplyBody = _Assert<OpenApiApplyRequest extends OpenApiApplyBody ? true : false>;
type _ImportPreviewBodyIsImportRequest = _Assert<
  OpenApiImportPreviewBody extends OpenApiImportRequest ? true : false
>;
type _ImportRequestIsImportPreviewBody = _Assert<
  OpenApiImportRequest extends OpenApiImportPreviewBody ? true : false
>;
type _ImportApplyBodyIsImportRequest = _Assert<OpenApiImportApplyBody extends OpenApiImportRequest ? true : false>;
type _ImportRequestIsImportApplyBody = _Assert<OpenApiImportRequest extends OpenApiImportApplyBody ? true : false>;
type _OpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _ListPathIsOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _PreviewOpIsPath = _Assert<OpenApiPreviewOp extends OpenApiPreviewPathPost ? true : false>;
type _PreviewPathIsOp = _Assert<OpenApiPreviewPathPost extends OpenApiPreviewOp ? true : false>;
type _ApplyOpIsPath = _Assert<OpenApiApplyOp extends OpenApiApplyPathPost ? true : false>;
type _ApplyPathIsOp = _Assert<OpenApiApplyPathPost extends OpenApiApplyOp ? true : false>;
type _ExportOpIsPath = _Assert<OpenApiExportOp extends OpenApiExportPathGet ? true : false>;
type _ExportPathIsOp = _Assert<OpenApiExportPathGet extends OpenApiExportOp ? true : false>;
type _ImportPreviewOpIsPath = _Assert<OpenApiImportPreviewOp extends OpenApiImportPreviewPathPost ? true : false>;
type _ImportPreviewPathIsOp = _Assert<OpenApiImportPreviewPathPost extends OpenApiImportPreviewOp ? true : false>;
type _ImportApplyOpIsPath = _Assert<OpenApiImportApplyOp extends OpenApiImportApplyPathPost ? true : false>;
type _ImportApplyPathIsOp = _Assert<OpenApiImportApplyPathPost extends OpenApiImportApplyOp ? true : false>;
type _ListOpHasNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _ExportOpHasNeverRequestBody = _Assert<OpenApiExportOp extends { requestBody?: never } ? true : false>;
type _ListPathPostNever = _Assert<
  paths['/api/v1/config-profiles/presets']['post'] extends never | undefined ? true : false
>;
type _ExportPathPostNever = _Assert<
  paths['/api/v1/config-profiles/export']['post'] extends never | undefined ? true : false
>;
type _PreviewPathGetNever = _Assert<
  paths['/api/v1/config-profiles/presets/{preset_id}/preview']['get'] extends never | undefined ? true : false
>;
type _ApplyPathGetNever = _Assert<
  paths['/api/v1/config-profiles/presets/{preset_id}/apply']['get'] extends never | undefined ? true : false
>;
type _ImportPreviewPathGetNever = _Assert<
  paths['/api/v1/config-profiles/import/preview']['get'] extends never | undefined ? true : false
>;
type _ImportApplyPathGetNever = _Assert<
  paths['/api/v1/config-profiles/import/apply']['get'] extends never | undefined ? true : false
>;
type _List200IsNotItem = _Assert<OpenApiListGet200 extends OpenApiItem ? false : true>;
type _Export200IsNotList = _Assert<OpenApiExportGet200 extends OpenApiList ? false : true>;
type _ListQueryNever = _Assert<OpenApiListOp['parameters']['query'] extends never | undefined ? true : false>;
type _ExportQueryNever = _Assert<OpenApiExportOp['parameters']['query'] extends never | undefined ? true : false>;

type _OpenApiAnchors = [
  _List200IsList,
  _ListIsList200,
  _Preview200IsPreview,
  _PreviewIsPreview200,
  _Apply200IsApply,
  _ApplyIsApply200,
  _Export200IsExport,
  _ExportIsExport200,
  _ImportPreview200IsImportPreview,
  _ImportPreviewIsImportPreview200,
  _ImportApply200IsImportApply,
  _ImportApplyIsImportApply200,
  _PreviewBodyIsApplyRequest,
  _ApplyRequestIsPreviewBody,
  _ApplyBodyIsApplyRequest,
  _ApplyRequestIsApplyBody,
  _ImportPreviewBodyIsImportRequest,
  _ImportRequestIsImportPreviewBody,
  _ImportApplyBodyIsImportRequest,
  _ImportRequestIsImportApplyBody,
  _OpIsPath,
  _ListPathIsOp,
  _PreviewOpIsPath,
  _PreviewPathIsOp,
  _ApplyOpIsPath,
  _ApplyPathIsOp,
  _ExportOpIsPath,
  _ExportPathIsOp,
  _ImportPreviewOpIsPath,
  _ImportPreviewPathIsOp,
  _ImportApplyOpIsPath,
  _ImportApplyPathIsOp,
  _ListOpHasNeverRequestBody,
  _ExportOpHasNeverRequestBody,
  _ListPathPostNever,
  _ExportPathPostNever,
  _PreviewPathGetNever,
  _ApplyPathGetNever,
  _ImportPreviewPathGetNever,
  _ImportApplyPathGetNever,
  _List200IsNotItem,
  _Export200IsNotList,
  _ListQueryNever,
  _ExportQueryNever,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type ConfigProfileChange = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiChange>, {
  key: string;
  fromValue: string;
  to: string;
}>>;

export type ConfigProfileDetection = Override<CamelizeKeys<OpenApiDetection>, {
  ollamaHealthy: boolean;
  modelPackPresent: boolean;
  cliDetected: string[];
  cloudReady: boolean;
}>;

export type ConfigPresetItem = Override<CamelizeKeys<OpenApiItem>, {
  id: string;
  displayName: string;
  description: string;
  tags: string[];
  preferenceOrder: string[];
  configValues: Record<string, string>;
  strategies: Record<string, unknown>;
  features: Record<string, unknown>;
  requirements: Record<string, unknown>;
  recommended: boolean;
  score: number;
  meetsRequirements: boolean;
}>;

export type ConfigPresetListResponse = Override<CamelizeKeys<OpenApiList>, {
  recommendedPresetId: string | null;
  detection: ConfigProfileDetection;
  presets: ConfigPresetItem[];
}>;

export type ConfigPresetPreviewResponse = Override<CamelizeKeys<OpenApiPreview>, {
  presetId: string;
  displayName: string;
  configVersion: string;
  features: Record<string, unknown>;
  changes: ConfigProfileChange[];
  changeCount: number;
}>;

export type ConfigPresetApplyResponse = Override<CamelizeKeys<OpenApiApply>, {
  presetId: string;
  displayName: string;
  applied: boolean;
  configVersion: string;
  newConfigVersion: string;
  updatedKeys: string[];
  changes: ConfigProfileChange[];
  features: Record<string, unknown>;
  message: string;
}>;

export type ConfigProfileExportResponse = Override<CamelizeKeys<OpenApiExport>, {
  content: string;
  configVersion: string;
  filename: string;
  keysExported: string[];
  keysRedacted: number;
}>;

export type ConfigProfileImportPreviewResponse = Override<CamelizeKeys<OpenApiImportPreview>, {
  valid: boolean;
  configVersion: string;
  name: string;
  displayName: string;
  description: string;
  features: Record<string, unknown>;
  changes: ConfigProfileChange[];
  changeCount: number;
  issues: Array<Record<string, unknown>>;
}>;

export type ConfigProfileImportApplyResponse = Override<CamelizeKeys<OpenApiImportApply>, {
  applied: boolean;
  configVersion: string;
  newConfigVersion: string;
  updatedKeys: string[];
  changes: ConfigProfileChange[];
  name: string;
  features: Record<string, unknown>;
  message: string;
}>;
