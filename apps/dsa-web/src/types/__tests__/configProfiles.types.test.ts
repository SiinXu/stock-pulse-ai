// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as ConfigProfiles from '../configProfiles';
import type {
  ConfigPresetApplyResponse,
  ConfigPresetItem,
  ConfigPresetListResponse,
  ConfigPresetPreviewResponse,
  ConfigProfileChange,
  ConfigProfileDetection,
  ConfigProfileExportResponse,
  ConfigProfileImportApplyResponse,
  ConfigProfileImportPreviewResponse,
} from '../configProfiles';

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

type PublicUiKeys =
  | keyof ConfigProfileChange
  | keyof ConfigProfileDetection
  | keyof ConfigPresetItem
  | keyof ConfigPresetListResponse
  | keyof ConfigPresetPreviewResponse
  | keyof ConfigPresetApplyResponse
  | keyof ConfigProfileExportResponse
  | keyof ConfigProfileImportPreviewResponse
  | keyof ConfigProfileImportApplyResponse;

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

type _UiHasFromValue = _Assert<'fromValue' extends keyof ConfigProfileChange ? true : false>;
type _UiHasDisplayName = _Assert<'displayName' extends keyof ConfigPresetItem ? true : false>;
type _UiHasPreferenceOrder = _Assert<'preferenceOrder' extends keyof ConfigPresetItem ? true : false>;
type _UiHasConfigValues = _Assert<'configValues' extends keyof ConfigPresetItem ? true : false>;
type _UiHasMeetsRequirements = _Assert<'meetsRequirements' extends keyof ConfigPresetItem ? true : false>;
type _UiHasRecommendedPresetId = _Assert<'recommendedPresetId' extends keyof ConfigPresetListResponse ? true : false>;
type _UiHasPresetId = _Assert<'presetId' extends keyof ConfigPresetPreviewResponse ? true : false>;
type _UiHasConfigVersion = _Assert<'configVersion' extends keyof ConfigPresetPreviewResponse ? true : false>;
type _UiHasChangeCount = _Assert<'changeCount' extends keyof ConfigPresetPreviewResponse ? true : false>;
type _UiHasNewConfigVersion = _Assert<'newConfigVersion' extends keyof ConfigPresetApplyResponse ? true : false>;
type _UiHasUpdatedKeys = _Assert<'updatedKeys' extends keyof ConfigPresetApplyResponse ? true : false>;
type _UiHasKeysExported = _Assert<'keysExported' extends keyof ConfigProfileExportResponse ? true : false>;
type _UiHasKeysRedacted = _Assert<'keysRedacted' extends keyof ConfigProfileExportResponse ? true : false>;
type _UiHasOllamaHealthy = _Assert<'ollamaHealthy' extends keyof ConfigProfileDetection ? true : false>;
type _UiHasModelPackPresent = _Assert<'modelPackPresent' extends keyof ConfigProfileDetection ? true : false>;
type _UiHasCliDetected = _Assert<'cliDetected' extends keyof ConfigProfileDetection ? true : false>;
type _UiHasCloudReady = _Assert<'cloudReady' extends keyof ConfigProfileDetection ? true : false>;

type _UiLacksFromValueSnake = _Assert<'from_value' extends keyof ConfigProfileChange ? false : true>;
type _UiLacksDisplayNameSnake = _Assert<'display_name' extends keyof ConfigPresetItem ? false : true>;
type _UiLacksPreferenceOrderSnake = _Assert<'preference_order' extends keyof ConfigPresetItem ? false : true>;
type _UiLacksConfigValuesSnake = _Assert<'config_values' extends keyof ConfigPresetItem ? false : true>;
type _UiLacksMeetsRequirementsSnake = _Assert<'meets_requirements' extends keyof ConfigPresetItem ? false : true>;
type _UiLacksRecommendedPresetIdSnake = _Assert<
  'recommended_preset_id' extends keyof ConfigPresetListResponse ? false : true
>;
type _UiLacksPresetIdSnake = _Assert<'preset_id' extends keyof ConfigPresetPreviewResponse ? false : true>;
type _UiLacksConfigVersionSnake = _Assert<'config_version' extends keyof ConfigPresetPreviewResponse ? false : true>;
type _UiLacksChangeCountSnake = _Assert<'change_count' extends keyof ConfigPresetPreviewResponse ? false : true>;
type _UiLacksNewConfigVersionSnake = _Assert<
  'new_config_version' extends keyof ConfigPresetApplyResponse ? false : true
>;
type _UiLacksUpdatedKeysSnake = _Assert<'updated_keys' extends keyof ConfigPresetApplyResponse ? false : true>;
type _UiLacksKeysExportedSnake = _Assert<'keys_exported' extends keyof ConfigProfileExportResponse ? false : true>;
type _UiLacksKeysRedactedSnake = _Assert<'keys_redacted' extends keyof ConfigProfileExportResponse ? false : true>;
type _UiLacksOllamaHealthySnake = _Assert<'ollama_healthy' extends keyof ConfigProfileDetection ? false : true>;
type _UiLacksModelPackPresentSnake = _Assert<
  'model_pack_present' extends keyof ConfigProfileDetection ? false : true
>;
type _UiLacksCliDetectedSnake = _Assert<'cli_detected' extends keyof ConfigProfileDetection ? false : true>;
type _UiLacksCloudReadySnake = _Assert<'cloud_ready' extends keyof ConfigProfileDetection ? false : true>;
type _UiLacksReloadNow = _Assert<'reloadNow' extends PublicUiKeys ? false : true>;
type _UiLacksReloadNowSnake = _Assert<'reload_now' extends PublicUiKeys ? false : true>;

type _GeneratedHasFromValueSnake = _Assert<'from_value' extends keyof OpenApiChange ? true : false>;
type _GeneratedHasDisplayNameSnake = _Assert<'display_name' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasPreferenceOrderSnake = _Assert<'preference_order' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasConfigValuesSnake = _Assert<'config_values' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasMeetsRequirementsSnake = _Assert<'meets_requirements' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasRecommendedPresetIdSnake = _Assert<'recommended_preset_id' extends keyof OpenApiList ? true : false>;
type _GeneratedHasPresetIdSnake = _Assert<'preset_id' extends keyof OpenApiPreview ? true : false>;
type _GeneratedHasConfigVersionSnake = _Assert<'config_version' extends keyof OpenApiPreview ? true : false>;
type _GeneratedHasChangeCountSnake = _Assert<'change_count' extends keyof OpenApiPreview ? true : false>;
type _GeneratedHasNewConfigVersionSnake = _Assert<'new_config_version' extends keyof OpenApiApply ? true : false>;
type _GeneratedHasUpdatedKeysSnake = _Assert<'updated_keys' extends keyof OpenApiApply ? true : false>;
type _GeneratedHasKeysExportedSnake = _Assert<'keys_exported' extends keyof OpenApiExport ? true : false>;
type _GeneratedHasKeysRedactedSnake = _Assert<'keys_redacted' extends keyof OpenApiExport ? true : false>;
type _GeneratedHasOllamaHealthySnake = _Assert<'ollama_healthy' extends keyof OpenApiDetection ? true : false>;
type _GeneratedHasModelPackPresentSnake = _Assert<'model_pack_present' extends keyof OpenApiDetection ? true : false>;
type _GeneratedHasCliDetectedSnake = _Assert<'cli_detected' extends keyof OpenApiDetection ? true : false>;
type _GeneratedHasCloudReadySnake = _Assert<'cloud_ready' extends keyof OpenApiDetection ? true : false>;
type _GeneratedApplyRequestHasReloadNow = _Assert<'reload_now' extends keyof OpenApiApplyRequest ? true : false>;
type _GeneratedImportRequestHasReloadNow = _Assert<'reload_now' extends keyof OpenApiImportRequest ? true : false>;

type _UiLacksFromValueCamelOnGenerated = _Assert<'fromValue' extends keyof OpenApiChange ? false : true>;
type _UiLacksDisplayNameCamelOnGenerated = _Assert<'displayName' extends keyof OpenApiItem ? false : true>;
type _UiLacksPresetIdCamelOnGenerated = _Assert<'presetId' extends keyof OpenApiPreview ? false : true>;
type _UiLacksReloadNowCamelOnGenerated = _Assert<'reloadNow' extends keyof OpenApiApplyRequest ? false : true>;

type _UiCliDetectedRequired = _Assert<
  IsOptional<ConfigProfileDetection, 'cliDetected'> extends false ? true : false
>;
type _GeneratedCliDetectedOptional = _Assert<IsOptional<OpenApiDetection, 'cli_detected'>>;
type _UiTagsRequired = _Assert<IsOptional<ConfigPresetItem, 'tags'> extends false ? true : false>;
type _GeneratedTagsOptional = _Assert<IsOptional<OpenApiItem, 'tags'>>;
type _UiPreferenceOrderRequired = _Assert<
  IsOptional<ConfigPresetItem, 'preferenceOrder'> extends false ? true : false
>;
type _GeneratedPreferenceOrderOptional = _Assert<IsOptional<OpenApiItem, 'preference_order'>>;
type _UiConfigValuesRequired = _Assert<IsOptional<ConfigPresetItem, 'configValues'> extends false ? true : false>;
type _GeneratedConfigValuesOptional = _Assert<IsOptional<OpenApiItem, 'config_values'>>;
type _UiStrategiesRequired = _Assert<IsOptional<ConfigPresetItem, 'strategies'> extends false ? true : false>;
type _GeneratedStrategiesOptional = _Assert<IsOptional<OpenApiItem, 'strategies'>>;
type _UiItemFeaturesRequired = _Assert<IsOptional<ConfigPresetItem, 'features'> extends false ? true : false>;
type _GeneratedItemFeaturesOptional = _Assert<IsOptional<OpenApiItem, 'features'>>;
type _UiRequirementsRequired = _Assert<IsOptional<ConfigPresetItem, 'requirements'> extends false ? true : false>;
type _GeneratedRequirementsOptional = _Assert<IsOptional<OpenApiItem, 'requirements'>>;
type _UiDetectionRequired = _Assert<IsOptional<ConfigPresetListResponse, 'detection'> extends false ? true : false>;
type _GeneratedDetectionOptional = _Assert<IsOptional<OpenApiList, 'detection'>>;
type _UiPresetsRequired = _Assert<IsOptional<ConfigPresetListResponse, 'presets'> extends false ? true : false>;
type _GeneratedPresetsOptional = _Assert<IsOptional<OpenApiList, 'presets'>>;
type _UiRecommendedRequired = _Assert<
  IsOptional<ConfigPresetListResponse, 'recommendedPresetId'> extends false ? true : false
>;
type _GeneratedRecommendedOptional = _Assert<IsOptional<OpenApiList, 'recommended_preset_id'>>;
type _UiPreviewFeaturesRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'features'> extends false ? true : false
>;
type _GeneratedPreviewFeaturesOptional = _Assert<IsOptional<OpenApiPreview, 'features'>>;
type _UiPreviewChangesRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'changes'> extends false ? true : false
>;
type _GeneratedPreviewChangesOptional = _Assert<IsOptional<OpenApiPreview, 'changes'>>;
type _UiApplyUpdatedKeysRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'updatedKeys'> extends false ? true : false
>;
type _GeneratedApplyUpdatedKeysOptional = _Assert<IsOptional<OpenApiApply, 'updated_keys'>>;
type _UiApplyChangesRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'changes'> extends false ? true : false
>;
type _GeneratedApplyChangesOptional = _Assert<IsOptional<OpenApiApply, 'changes'>>;
type _UiApplyFeaturesRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'features'> extends false ? true : false
>;
type _GeneratedApplyFeaturesOptional = _Assert<IsOptional<OpenApiApply, 'features'>>;
type _UiKeysExportedRequired = _Assert<
  IsOptional<ConfigProfileExportResponse, 'keysExported'> extends false ? true : false
>;
type _GeneratedKeysExportedOptional = _Assert<IsOptional<OpenApiExport, 'keys_exported'>>;
type _UiImportPreviewFeaturesRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'features'> extends false ? true : false
>;
type _GeneratedImportPreviewFeaturesOptional = _Assert<IsOptional<OpenApiImportPreview, 'features'>>;
type _UiImportPreviewChangesRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'changes'> extends false ? true : false
>;
type _GeneratedImportPreviewChangesOptional = _Assert<IsOptional<OpenApiImportPreview, 'changes'>>;
type _UiImportPreviewIssuesRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'issues'> extends false ? true : false
>;
type _GeneratedImportPreviewIssuesOptional = _Assert<IsOptional<OpenApiImportPreview, 'issues'>>;
type _UiImportApplyUpdatedKeysRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'updatedKeys'> extends false ? true : false
>;
type _GeneratedImportApplyUpdatedKeysOptional = _Assert<IsOptional<OpenApiImportApply, 'updated_keys'>>;
type _UiImportApplyChangesRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'changes'> extends false ? true : false
>;
type _GeneratedImportApplyChangesOptional = _Assert<IsOptional<OpenApiImportApply, 'changes'>>;
type _UiImportApplyFeaturesRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'features'> extends false ? true : false
>;
type _GeneratedImportApplyFeaturesOptional = _Assert<IsOptional<OpenApiImportApply, 'features'>>;

type _UiKeyRequired = _Assert<IsOptional<ConfigProfileChange, 'key'> extends false ? true : false>;
type _GeneratedKeyRequired = _Assert<IsOptional<OpenApiChange, 'key'> extends false ? true : false>;
type _UiFromValueRequired = _Assert<IsOptional<ConfigProfileChange, 'fromValue'> extends false ? true : false>;
type _GeneratedFromValueRequired = _Assert<IsOptional<OpenApiChange, 'from_value'> extends false ? true : false>;
type _UiToRequired = _Assert<IsOptional<ConfigProfileChange, 'to'> extends false ? true : false>;
type _GeneratedToRequired = _Assert<IsOptional<OpenApiChange, 'to'> extends false ? true : false>;
type _UiOllamaHealthyRequired = _Assert<
  IsOptional<ConfigProfileDetection, 'ollamaHealthy'> extends false ? true : false
>;
type _GeneratedOllamaHealthyRequired = _Assert<
  IsOptional<OpenApiDetection, 'ollama_healthy'> extends false ? true : false
>;
type _UiModelPackPresentRequired = _Assert<
  IsOptional<ConfigProfileDetection, 'modelPackPresent'> extends false ? true : false
>;
type _GeneratedModelPackPresentRequired = _Assert<
  IsOptional<OpenApiDetection, 'model_pack_present'> extends false ? true : false
>;
type _UiCloudReadyRequired = _Assert<IsOptional<ConfigProfileDetection, 'cloudReady'> extends false ? true : false>;
type _GeneratedCloudReadyRequired = _Assert<
  IsOptional<OpenApiDetection, 'cloud_ready'> extends false ? true : false
>;
type _UiItemIdRequired = _Assert<IsOptional<ConfigPresetItem, 'id'> extends false ? true : false>;
type _GeneratedItemIdRequired = _Assert<IsOptional<OpenApiItem, 'id'> extends false ? true : false>;
type _UiItemDisplayNameRequired = _Assert<
  IsOptional<ConfigPresetItem, 'displayName'> extends false ? true : false
>;
type _GeneratedItemDisplayNameRequired = _Assert<
  IsOptional<OpenApiItem, 'display_name'> extends false ? true : false
>;
type _UiItemDescriptionRequired = _Assert<
  IsOptional<ConfigPresetItem, 'description'> extends false ? true : false
>;
type _GeneratedItemDescriptionRequired = _Assert<
  IsOptional<OpenApiItem, 'description'> extends false ? true : false
>;
type _UiRecommendedFlagRequired = _Assert<
  IsOptional<ConfigPresetItem, 'recommended'> extends false ? true : false
>;
type _GeneratedRecommendedFlagRequired = _Assert<
  IsOptional<OpenApiItem, 'recommended'> extends false ? true : false
>;
type _UiScoreRequired = _Assert<IsOptional<ConfigPresetItem, 'score'> extends false ? true : false>;
type _GeneratedScoreRequired = _Assert<IsOptional<OpenApiItem, 'score'> extends false ? true : false>;
type _UiMeetsRequirementsRequired = _Assert<
  IsOptional<ConfigPresetItem, 'meetsRequirements'> extends false ? true : false
>;
type _GeneratedMeetsRequirementsRequired = _Assert<
  IsOptional<OpenApiItem, 'meets_requirements'> extends false ? true : false
>;
type _UiPreviewPresetIdRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'presetId'> extends false ? true : false
>;
type _GeneratedPreviewPresetIdRequired = _Assert<
  IsOptional<OpenApiPreview, 'preset_id'> extends false ? true : false
>;
type _UiPreviewDisplayNameRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'displayName'> extends false ? true : false
>;
type _GeneratedPreviewDisplayNameRequired = _Assert<
  IsOptional<OpenApiPreview, 'display_name'> extends false ? true : false
>;
type _UiPreviewConfigVersionRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'configVersion'> extends false ? true : false
>;
type _GeneratedPreviewConfigVersionRequired = _Assert<
  IsOptional<OpenApiPreview, 'config_version'> extends false ? true : false
>;
type _UiPreviewChangeCountRequired = _Assert<
  IsOptional<ConfigPresetPreviewResponse, 'changeCount'> extends false ? true : false
>;
type _GeneratedPreviewChangeCountRequired = _Assert<
  IsOptional<OpenApiPreview, 'change_count'> extends false ? true : false
>;
type _UiApplyPresetIdRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'presetId'> extends false ? true : false
>;
type _GeneratedApplyPresetIdRequired = _Assert<IsOptional<OpenApiApply, 'preset_id'> extends false ? true : false>;
type _UiApplyDisplayNameRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'displayName'> extends false ? true : false
>;
type _GeneratedApplyDisplayNameRequired = _Assert<
  IsOptional<OpenApiApply, 'display_name'> extends false ? true : false
>;
type _UiApplyAppliedRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'applied'> extends false ? true : false
>;
type _GeneratedApplyAppliedRequired = _Assert<IsOptional<OpenApiApply, 'applied'> extends false ? true : false>;
type _UiApplyConfigVersionRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'configVersion'> extends false ? true : false
>;
type _GeneratedApplyConfigVersionRequired = _Assert<
  IsOptional<OpenApiApply, 'config_version'> extends false ? true : false
>;
type _UiApplyNewConfigVersionRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'newConfigVersion'> extends false ? true : false
>;
type _GeneratedApplyNewConfigVersionRequired = _Assert<
  IsOptional<OpenApiApply, 'new_config_version'> extends false ? true : false
>;
type _UiApplyMessageRequired = _Assert<
  IsOptional<ConfigPresetApplyResponse, 'message'> extends false ? true : false
>;
type _GeneratedApplyMessageRequired = _Assert<IsOptional<OpenApiApply, 'message'> extends false ? true : false>;
type _UiExportContentRequired = _Assert<
  IsOptional<ConfigProfileExportResponse, 'content'> extends false ? true : false
>;
type _GeneratedExportContentRequired = _Assert<IsOptional<OpenApiExport, 'content'> extends false ? true : false>;
type _UiExportConfigVersionRequired = _Assert<
  IsOptional<ConfigProfileExportResponse, 'configVersion'> extends false ? true : false
>;
type _GeneratedExportConfigVersionRequired = _Assert<
  IsOptional<OpenApiExport, 'config_version'> extends false ? true : false
>;
type _UiExportFilenameRequired = _Assert<
  IsOptional<ConfigProfileExportResponse, 'filename'> extends false ? true : false
>;
type _GeneratedExportFilenameRequired = _Assert<
  IsOptional<OpenApiExport, 'filename'> extends false ? true : false
>;
type _UiExportKeysRedactedRequired = _Assert<
  IsOptional<ConfigProfileExportResponse, 'keysRedacted'> extends false ? true : false
>;
type _GeneratedExportKeysRedactedRequired = _Assert<
  IsOptional<OpenApiExport, 'keys_redacted'> extends false ? true : false
>;
type _UiImportPreviewValidRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'valid'> extends false ? true : false
>;
type _GeneratedImportPreviewValidRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'valid'> extends false ? true : false
>;
type _UiImportPreviewConfigVersionRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'configVersion'> extends false ? true : false
>;
type _GeneratedImportPreviewConfigVersionRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'config_version'> extends false ? true : false
>;
type _UiImportPreviewNameRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'name'> extends false ? true : false
>;
type _GeneratedImportPreviewNameRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'name'> extends false ? true : false
>;
type _UiImportPreviewDisplayNameRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'displayName'> extends false ? true : false
>;
type _GeneratedImportPreviewDisplayNameRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'display_name'> extends false ? true : false
>;
type _UiImportPreviewDescriptionRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'description'> extends false ? true : false
>;
type _GeneratedImportPreviewDescriptionRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'description'> extends false ? true : false
>;
type _UiImportPreviewChangeCountRequired = _Assert<
  IsOptional<ConfigProfileImportPreviewResponse, 'changeCount'> extends false ? true : false
>;
type _GeneratedImportPreviewChangeCountRequired = _Assert<
  IsOptional<OpenApiImportPreview, 'change_count'> extends false ? true : false
>;
type _UiImportApplyAppliedRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'applied'> extends false ? true : false
>;
type _GeneratedImportApplyAppliedRequired = _Assert<
  IsOptional<OpenApiImportApply, 'applied'> extends false ? true : false
>;
type _UiImportApplyConfigVersionRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'configVersion'> extends false ? true : false
>;
type _GeneratedImportApplyConfigVersionRequired = _Assert<
  IsOptional<OpenApiImportApply, 'config_version'> extends false ? true : false
>;
type _UiImportApplyNewConfigVersionRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'newConfigVersion'> extends false ? true : false
>;
type _GeneratedImportApplyNewConfigVersionRequired = _Assert<
  IsOptional<OpenApiImportApply, 'new_config_version'> extends false ? true : false
>;
type _UiImportApplyNameRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'name'> extends false ? true : false
>;
type _GeneratedImportApplyNameRequired = _Assert<
  IsOptional<OpenApiImportApply, 'name'> extends false ? true : false
>;
type _UiImportApplyMessageRequired = _Assert<
  IsOptional<ConfigProfileImportApplyResponse, 'message'> extends false ? true : false
>;
type _GeneratedImportApplyMessageRequired = _Assert<
  IsOptional<OpenApiImportApply, 'message'> extends false ? true : false
>;

type _UiRecommendedAllowsNull = _Assert<
  null extends ConfigPresetListResponse['recommendedPresetId'] ? true : false
>;
type _UiRecommendedRejectsUndefined = _Assert<
  undefined extends ConfigPresetListResponse['recommendedPresetId'] ? false : true
>;
type _GeneratedRecommendedAllowsNull = _Assert<null extends OpenApiList['recommended_preset_id'] ? true : false>;

type _OmitTags = _Assert<Omit<ConfigPresetItem, 'tags'> extends ConfigPresetItem ? false : true>;
type _OmitGeneratedTags = _Assert<Omit<OpenApiItem, 'tags'> extends OpenApiItem ? true : false>;
type _OmitPresets = _Assert<Omit<ConfigPresetListResponse, 'presets'> extends ConfigPresetListResponse ? false : true>;
type _OmitGeneratedPresets = _Assert<Omit<OpenApiList, 'presets'> extends OpenApiList ? true : false>;
type _OmitRecommended = _Assert<
  Omit<ConfigPresetListResponse, 'recommendedPresetId'> extends ConfigPresetListResponse ? false : true
>;
type _OmitGeneratedRecommended = _Assert<
  Omit<OpenApiList, 'recommended_preset_id'> extends OpenApiList ? true : false
>;
type _OmitCliDetected = _Assert<
  Omit<ConfigProfileDetection, 'cliDetected'> extends ConfigProfileDetection ? false : true
>;
type _OmitGeneratedCliDetected = _Assert<Omit<OpenApiDetection, 'cli_detected'> extends OpenApiDetection ? true : false>;
type _OmitDetection = _Assert<
  Omit<ConfigPresetListResponse, 'detection'> extends ConfigPresetListResponse ? false : true
>;
type _OmitGeneratedDetection = _Assert<Omit<OpenApiList, 'detection'> extends OpenApiList ? true : false>;
type _OmitPreferenceOrder = _Assert<
  Omit<ConfigPresetItem, 'preferenceOrder'> extends ConfigPresetItem ? false : true
>;
type _OmitGeneratedPreferenceOrder = _Assert<
  Omit<OpenApiItem, 'preference_order'> extends OpenApiItem ? true : false
>;
type _OmitKey = _Assert<Omit<ConfigProfileChange, 'key'> extends ConfigProfileChange ? false : true>;
type _OmitGeneratedKey = _Assert<Omit<OpenApiChange, 'key'> extends OpenApiChange ? false : true>;
type _OmitFromValue = _Assert<Omit<ConfigProfileChange, 'fromValue'> extends ConfigProfileChange ? false : true>;
type _OmitGeneratedFromValue = _Assert<Omit<OpenApiChange, 'from_value'> extends OpenApiChange ? false : true>;
type _OmitScore = _Assert<Omit<ConfigPresetItem, 'score'> extends ConfigPresetItem ? false : true>;
type _OmitGeneratedScore = _Assert<Omit<OpenApiItem, 'score'> extends OpenApiItem ? false : true>;
type _OmitPreviewChangeCount = _Assert<
  Omit<ConfigPresetPreviewResponse, 'changeCount'> extends ConfigPresetPreviewResponse ? false : true
>;
type _OmitGeneratedPreviewChangeCount = _Assert<
  Omit<OpenApiPreview, 'change_count'> extends OpenApiPreview ? false : true
>;
type _OmitExportKeysRedacted = _Assert<
  Omit<ConfigProfileExportResponse, 'keysRedacted'> extends ConfigProfileExportResponse ? false : true
>;
type _OmitGeneratedExportKeysRedacted = _Assert<
  Omit<OpenApiExport, 'keys_redacted'> extends OpenApiExport ? false : true
>;
type _OmitApplyMessage = _Assert<
  Omit<ConfigPresetApplyResponse, 'message'> extends ConfigPresetApplyResponse ? false : true
>;
type _OmitGeneratedApplyMessage = _Assert<Omit<OpenApiApply, 'message'> extends OpenApiApply ? false : true>;

type _UiListIsNotGeneratedAlias = _Assert<ConfigPresetListResponse extends OpenApiList ? false : true>;
type _GeneratedListIsNotUi = _Assert<OpenApiList extends ConfigPresetListResponse ? false : true>;
type _UiItemIsNotGeneratedAlias = _Assert<ConfigPresetItem extends OpenApiItem ? false : true>;
type _GeneratedItemIsNotUi = _Assert<OpenApiItem extends ConfigPresetItem ? false : true>;
type _UiChangeIsNotGeneratedAlias = _Assert<ConfigProfileChange extends OpenApiChange ? false : true>;
type _GeneratedChangeIsNotUi = _Assert<OpenApiChange extends ConfigProfileChange ? false : true>;
type _UiDetectionIsNotGeneratedAlias = _Assert<ConfigProfileDetection extends OpenApiDetection ? false : true>;
type _CamelApplyHasReloadNow = _Assert<'reloadNow' extends keyof CamelizeKeys<OpenApiApplyRequest> ? true : false>;
type _CamelApplyReloadNowRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiApplyRequest>, 'reloadNow'> extends false ? true : false
>;

const change: ConfigProfileChange = { key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' };
const detection: ConfigProfileDetection = {
  ollamaHealthy: true,
  modelPackPresent: false,
  cliDetected: [],
  cloudReady: false,
};
const item: ConfigPresetItem = {
  id: 'local-first',
  displayName: 'Local-first (Ollama / Model Pack)',
  description: 'Prefer local models',
  tags: ['local'],
  preferenceOrder: ['ollama'],
  configValues: {},
  strategies: {},
  features: { beginner_mode: true },
  requirements: {},
  recommended: true,
  score: 110,
  meetsRequirements: true,
};
const list: ConfigPresetListResponse = {
  recommendedPresetId: 'local-first',
  detection,
  presets: [item],
};
const listNullRecommended: ConfigPresetListResponse = {
  recommendedPresetId: null,
  detection,
  presets: [],
};
const preview: ConfigPresetPreviewResponse = {
  presetId: 'local-first',
  displayName: 'Local-first',
  configVersion: 'v1',
  features: {},
  changes: [change],
  changeCount: 1,
};
const applied: ConfigPresetApplyResponse = {
  presetId: 'local-first',
  displayName: 'Local-first',
  applied: true,
  configVersion: 'v1',
  newConfigVersion: 'v2',
  updatedKeys: ['GENERATION_BACKEND'],
  changes: [],
  features: {},
  message: 'ok',
};
const exported: ConfigProfileExportResponse = {
  content: 'apiVersion: stockpulse/v1\n',
  configVersion: 'v1',
  filename: 'stockpulse-profile-current.yaml',
  keysExported: ['GENERATION_BACKEND'],
  keysRedacted: 3,
};
const importPreview: ConfigProfileImportPreviewResponse = {
  valid: true,
  configVersion: 'v1',
  name: 'local-first',
  displayName: 'Local-first',
  description: 'Prefer local models',
  features: {},
  changes: [change],
  changeCount: 1,
  issues: [],
};
const importApply: ConfigProfileImportApplyResponse = {
  applied: true,
  configVersion: 'v1',
  newConfigVersion: 'v2',
  updatedKeys: ['GENERATION_BACKEND'],
  changes: [],
  name: 'local-first',
  features: {},
  message: 'ok',
};

type SnakeChange = {
  key: string;
  from_value: string;
  to: string;
};
type SnakeList = {
  recommended_preset_id: string | null;
  detection: OpenApiDetection;
  presets: OpenApiItem[];
};
type _SnakeChangeMatchesGenerated = _Assert<SnakeChange extends OpenApiChange ? true : false>;
type _SnakeChangeDoesNotMatchUi = _Assert<SnakeChange extends ConfigProfileChange ? false : true>;
type _SnakeListMatchesGenerated = _Assert<SnakeList extends OpenApiList ? true : false>;
type _SnakeListDoesNotMatchUi = _Assert<SnakeList extends ConfigPresetListResponse ? false : true>;

type _NarrowChangeAssignable = _Assert<typeof change extends ConfigProfileChange ? true : false>;
type _NarrowDetectionAssignable = _Assert<typeof detection extends ConfigProfileDetection ? true : false>;
type _NarrowItemAssignable = _Assert<typeof item extends ConfigPresetItem ? true : false>;
type _NarrowListAssignable = _Assert<typeof list extends ConfigPresetListResponse ? true : false>;
type _NarrowListNullAssignable = _Assert<typeof listNullRecommended extends ConfigPresetListResponse ? true : false>;
type _NarrowPreviewAssignable = _Assert<typeof preview extends ConfigPresetPreviewResponse ? true : false>;
type _NarrowApplyAssignable = _Assert<typeof applied extends ConfigPresetApplyResponse ? true : false>;
type _NarrowExportAssignable = _Assert<typeof exported extends ConfigProfileExportResponse ? true : false>;
type _NarrowImportPreviewAssignable = _Assert<
  typeof importPreview extends ConfigProfileImportPreviewResponse ? true : false
>;
type _NarrowImportApplyAssignable = _Assert<
  typeof importApply extends ConfigProfileImportApplyResponse ? true : false
>;

type _CompileTimePins = [
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
  _UiHasFromValue,
  _UiHasDisplayName,
  _UiHasPreferenceOrder,
  _UiHasConfigValues,
  _UiHasMeetsRequirements,
  _UiHasRecommendedPresetId,
  _UiHasPresetId,
  _UiHasConfigVersion,
  _UiHasChangeCount,
  _UiHasNewConfigVersion,
  _UiHasUpdatedKeys,
  _UiHasKeysExported,
  _UiHasKeysRedacted,
  _UiHasOllamaHealthy,
  _UiHasModelPackPresent,
  _UiHasCliDetected,
  _UiHasCloudReady,
  _UiLacksFromValueSnake,
  _UiLacksDisplayNameSnake,
  _UiLacksPreferenceOrderSnake,
  _UiLacksConfigValuesSnake,
  _UiLacksMeetsRequirementsSnake,
  _UiLacksRecommendedPresetIdSnake,
  _UiLacksPresetIdSnake,
  _UiLacksConfigVersionSnake,
  _UiLacksChangeCountSnake,
  _UiLacksNewConfigVersionSnake,
  _UiLacksUpdatedKeysSnake,
  _UiLacksKeysExportedSnake,
  _UiLacksKeysRedactedSnake,
  _UiLacksOllamaHealthySnake,
  _UiLacksModelPackPresentSnake,
  _UiLacksCliDetectedSnake,
  _UiLacksCloudReadySnake,
  _UiLacksReloadNow,
  _UiLacksReloadNowSnake,
  _GeneratedHasFromValueSnake,
  _GeneratedHasDisplayNameSnake,
  _GeneratedHasPreferenceOrderSnake,
  _GeneratedHasConfigValuesSnake,
  _GeneratedHasMeetsRequirementsSnake,
  _GeneratedHasRecommendedPresetIdSnake,
  _GeneratedHasPresetIdSnake,
  _GeneratedHasConfigVersionSnake,
  _GeneratedHasChangeCountSnake,
  _GeneratedHasNewConfigVersionSnake,
  _GeneratedHasUpdatedKeysSnake,
  _GeneratedHasKeysExportedSnake,
  _GeneratedHasKeysRedactedSnake,
  _GeneratedHasOllamaHealthySnake,
  _GeneratedHasModelPackPresentSnake,
  _GeneratedHasCliDetectedSnake,
  _GeneratedHasCloudReadySnake,
  _GeneratedApplyRequestHasReloadNow,
  _GeneratedImportRequestHasReloadNow,
  _UiLacksFromValueCamelOnGenerated,
  _UiLacksDisplayNameCamelOnGenerated,
  _UiLacksPresetIdCamelOnGenerated,
  _UiLacksReloadNowCamelOnGenerated,
  _UiCliDetectedRequired,
  _GeneratedCliDetectedOptional,
  _UiTagsRequired,
  _GeneratedTagsOptional,
  _UiPreferenceOrderRequired,
  _GeneratedPreferenceOrderOptional,
  _UiConfigValuesRequired,
  _GeneratedConfigValuesOptional,
  _UiStrategiesRequired,
  _GeneratedStrategiesOptional,
  _UiItemFeaturesRequired,
  _GeneratedItemFeaturesOptional,
  _UiRequirementsRequired,
  _GeneratedRequirementsOptional,
  _UiDetectionRequired,
  _GeneratedDetectionOptional,
  _UiPresetsRequired,
  _GeneratedPresetsOptional,
  _UiRecommendedRequired,
  _GeneratedRecommendedOptional,
  _UiPreviewFeaturesRequired,
  _GeneratedPreviewFeaturesOptional,
  _UiPreviewChangesRequired,
  _GeneratedPreviewChangesOptional,
  _UiApplyUpdatedKeysRequired,
  _GeneratedApplyUpdatedKeysOptional,
  _UiApplyChangesRequired,
  _GeneratedApplyChangesOptional,
  _UiApplyFeaturesRequired,
  _GeneratedApplyFeaturesOptional,
  _UiKeysExportedRequired,
  _GeneratedKeysExportedOptional,
  _UiImportPreviewFeaturesRequired,
  _GeneratedImportPreviewFeaturesOptional,
  _UiImportPreviewChangesRequired,
  _GeneratedImportPreviewChangesOptional,
  _UiImportPreviewIssuesRequired,
  _GeneratedImportPreviewIssuesOptional,
  _UiImportApplyUpdatedKeysRequired,
  _GeneratedImportApplyUpdatedKeysOptional,
  _UiImportApplyChangesRequired,
  _GeneratedImportApplyChangesOptional,
  _UiImportApplyFeaturesRequired,
  _GeneratedImportApplyFeaturesOptional,
  _UiKeyRequired,
  _GeneratedKeyRequired,
  _UiFromValueRequired,
  _GeneratedFromValueRequired,
  _UiToRequired,
  _GeneratedToRequired,
  _UiOllamaHealthyRequired,
  _GeneratedOllamaHealthyRequired,
  _UiModelPackPresentRequired,
  _GeneratedModelPackPresentRequired,
  _UiCloudReadyRequired,
  _GeneratedCloudReadyRequired,
  _UiItemIdRequired,
  _GeneratedItemIdRequired,
  _UiItemDisplayNameRequired,
  _GeneratedItemDisplayNameRequired,
  _UiItemDescriptionRequired,
  _GeneratedItemDescriptionRequired,
  _UiRecommendedFlagRequired,
  _GeneratedRecommendedFlagRequired,
  _UiScoreRequired,
  _GeneratedScoreRequired,
  _UiMeetsRequirementsRequired,
  _GeneratedMeetsRequirementsRequired,
  _UiPreviewPresetIdRequired,
  _GeneratedPreviewPresetIdRequired,
  _UiPreviewDisplayNameRequired,
  _GeneratedPreviewDisplayNameRequired,
  _UiPreviewConfigVersionRequired,
  _GeneratedPreviewConfigVersionRequired,
  _UiPreviewChangeCountRequired,
  _GeneratedPreviewChangeCountRequired,
  _UiApplyPresetIdRequired,
  _GeneratedApplyPresetIdRequired,
  _UiApplyDisplayNameRequired,
  _GeneratedApplyDisplayNameRequired,
  _UiApplyAppliedRequired,
  _GeneratedApplyAppliedRequired,
  _UiApplyConfigVersionRequired,
  _GeneratedApplyConfigVersionRequired,
  _UiApplyNewConfigVersionRequired,
  _GeneratedApplyNewConfigVersionRequired,
  _UiApplyMessageRequired,
  _GeneratedApplyMessageRequired,
  _UiExportContentRequired,
  _GeneratedExportContentRequired,
  _UiExportConfigVersionRequired,
  _GeneratedExportConfigVersionRequired,
  _UiExportFilenameRequired,
  _GeneratedExportFilenameRequired,
  _UiExportKeysRedactedRequired,
  _GeneratedExportKeysRedactedRequired,
  _UiImportPreviewValidRequired,
  _GeneratedImportPreviewValidRequired,
  _UiImportPreviewConfigVersionRequired,
  _GeneratedImportPreviewConfigVersionRequired,
  _UiImportPreviewNameRequired,
  _GeneratedImportPreviewNameRequired,
  _UiImportPreviewDisplayNameRequired,
  _GeneratedImportPreviewDisplayNameRequired,
  _UiImportPreviewDescriptionRequired,
  _GeneratedImportPreviewDescriptionRequired,
  _UiImportPreviewChangeCountRequired,
  _GeneratedImportPreviewChangeCountRequired,
  _UiImportApplyAppliedRequired,
  _GeneratedImportApplyAppliedRequired,
  _UiImportApplyConfigVersionRequired,
  _GeneratedImportApplyConfigVersionRequired,
  _UiImportApplyNewConfigVersionRequired,
  _GeneratedImportApplyNewConfigVersionRequired,
  _UiImportApplyNameRequired,
  _GeneratedImportApplyNameRequired,
  _UiImportApplyMessageRequired,
  _GeneratedImportApplyMessageRequired,
  _UiRecommendedAllowsNull,
  _UiRecommendedRejectsUndefined,
  _GeneratedRecommendedAllowsNull,
  _OmitTags,
  _OmitGeneratedTags,
  _OmitPresets,
  _OmitGeneratedPresets,
  _OmitRecommended,
  _OmitGeneratedRecommended,
  _OmitCliDetected,
  _OmitGeneratedCliDetected,
  _OmitDetection,
  _OmitGeneratedDetection,
  _OmitPreferenceOrder,
  _OmitGeneratedPreferenceOrder,
  _OmitKey,
  _OmitGeneratedKey,
  _OmitFromValue,
  _OmitGeneratedFromValue,
  _OmitScore,
  _OmitGeneratedScore,
  _OmitPreviewChangeCount,
  _OmitGeneratedPreviewChangeCount,
  _OmitExportKeysRedacted,
  _OmitGeneratedExportKeysRedacted,
  _OmitApplyMessage,
  _OmitGeneratedApplyMessage,
  _UiListIsNotGeneratedAlias,
  _GeneratedListIsNotUi,
  _UiItemIsNotGeneratedAlias,
  _GeneratedItemIsNotUi,
  _UiChangeIsNotGeneratedAlias,
  _GeneratedChangeIsNotUi,
  _UiDetectionIsNotGeneratedAlias,
  _CamelApplyHasReloadNow,
  _CamelApplyReloadNowRequired,
  _SnakeChangeMatchesGenerated,
  _SnakeChangeDoesNotMatchUi,
  _SnakeListMatchesGenerated,
  _SnakeListDoesNotMatchUi,
  _NarrowChangeAssignable,
  _NarrowDetectionAssignable,
  _NarrowItemAssignable,
  _NarrowListAssignable,
  _NarrowListNullAssignable,
  _NarrowPreviewAssignable,
  _NarrowApplyAssignable,
  _NarrowExportAssignable,
  _NarrowImportPreviewAssignable,
  _NarrowImportApplyAssignable,
];

describe('configProfiles OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...ConfigProfiles }).toEqual({});
    expect(Object.keys(ConfigProfiles)).toEqual([]);
    expect(Object.getOwnPropertyNames(ConfigProfiles)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON and request bodies to the generated components', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiPreviewPost200>().toEqualTypeOf<OpenApiPreview>();
    expectTypeOf<OpenApiApplyPost200>().toEqualTypeOf<OpenApiApply>();
    expectTypeOf<OpenApiExportGet200>().toEqualTypeOf<OpenApiExport>();
    expectTypeOf<OpenApiImportPreviewPost200>().toEqualTypeOf<OpenApiImportPreview>();
    expectTypeOf<OpenApiImportApplyPost200>().toEqualTypeOf<OpenApiImportApply>();
    expectTypeOf<OpenApiPreviewBody>().toEqualTypeOf<OpenApiApplyRequest>();
    expectTypeOf<OpenApiApplyBody>().toEqualTypeOf<OpenApiApplyRequest>();
    expectTypeOf<OpenApiImportPreviewBody>().toEqualTypeOf<OpenApiImportRequest>();
    expectTypeOf<OpenApiImportApplyBody>().toEqualTypeOf<OpenApiImportRequest>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiPreviewOp>().toEqualTypeOf<OpenApiPreviewPathPost>();
    expectTypeOf<OpenApiApplyOp>().toEqualTypeOf<OpenApiApplyPathPost>();
    expectTypeOf<OpenApiExportOp>().toEqualTypeOf<OpenApiExportPathGet>();
    expectTypeOf<OpenApiImportPreviewOp>().toEqualTypeOf<OpenApiImportPreviewPathPost>();
    expectTypeOf<OpenApiImportApplyOp>().toEqualTypeOf<OpenApiImportApplyPathPost>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof ConfigProfileChange>().not.toMatchTypeOf<'from_value'>();
    expectTypeOf<keyof ConfigPresetItem>().not.toMatchTypeOf<
      'display_name' | 'preference_order' | 'config_values' | 'meets_requirements'
    >();
    expectTypeOf<keyof ConfigPresetListResponse>().not.toMatchTypeOf<'recommended_preset_id'>();
    expectTypeOf<keyof ConfigPresetPreviewResponse>().not.toMatchTypeOf<
      'preset_id' | 'config_version' | 'change_count'
    >();
    expectTypeOf<keyof ConfigPresetApplyResponse>().not.toMatchTypeOf<
      'new_config_version' | 'updated_keys'
    >();
    expectTypeOf<keyof ConfigProfileExportResponse>().not.toMatchTypeOf<'keys_exported' | 'keys_redacted'>();
    expectTypeOf<keyof ConfigProfileDetection>().not.toMatchTypeOf<
      'ollama_healthy' | 'model_pack_present' | 'cli_detected' | 'cloud_ready'
    >();
    expectTypeOf<PublicUiKeys>().not.toMatchTypeOf<'reloadNow' | 'reload_now'>();

    type UiHasFromValue = 'fromValue' extends keyof ConfigProfileChange ? true : false;
    type UiHasFromValueSnake = 'from_value' extends keyof ConfigProfileChange ? true : false;
    type GeneratedHasFromValueSnake = 'from_value' extends keyof OpenApiChange ? true : false;
    type UiHasTags = 'tags' extends keyof ConfigPresetItem ? true : false;
    type UiHasRecommended = 'recommendedPresetId' extends keyof ConfigPresetListResponse ? true : false;
    type UiHasReloadNow = 'reloadNow' extends PublicUiKeys ? true : false;

    expectTypeOf<UiHasFromValue>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFromValueSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasFromValueSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasTags>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRecommended>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReloadNow>().toEqualTypeOf<false>();
  });

  it('keeps arrays, detection, and recommendedPresetId required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<ConfigPresetItem, 'tags'>>().not.toMatchTypeOf<ConfigPresetItem>();
    expectTypeOf<Omit<OpenApiItem, 'tags'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<ConfigPresetListResponse, 'presets'>>().not.toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf<Omit<OpenApiList, 'presets'>>().toMatchTypeOf<OpenApiList>();
    expectTypeOf<Omit<ConfigPresetListResponse, 'recommendedPresetId'>>().not.toMatchTypeOf<
      ConfigPresetListResponse
    >();
    expectTypeOf<Omit<OpenApiList, 'recommended_preset_id'>>().toMatchTypeOf<OpenApiList>();
    expectTypeOf<Omit<ConfigProfileDetection, 'cliDetected'>>().not.toMatchTypeOf<ConfigProfileDetection>();
    expectTypeOf<Omit<OpenApiDetection, 'cli_detected'>>().toMatchTypeOf<OpenApiDetection>();
    expectTypeOf<Omit<ConfigPresetListResponse, 'detection'>>().not.toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf<Omit<OpenApiList, 'detection'>>().toMatchTypeOf<OpenApiList>();
    expectTypeOf<Omit<ConfigProfileChange, 'key'>>().not.toMatchTypeOf<ConfigProfileChange>();
    expectTypeOf<Omit<OpenApiChange, 'key'>>().not.toMatchTypeOf<OpenApiChange>();
  });

  it('still accepts the narrow existing fixtures, including ConfigPresetsPanel payload', () => {
    expectTypeOf(change).toMatchTypeOf<ConfigProfileChange>();
    expectTypeOf(detection).toMatchTypeOf<ConfigProfileDetection>();
    expectTypeOf(item).toMatchTypeOf<ConfigPresetItem>();
    expectTypeOf(list).toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf(listNullRecommended).toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf(preview).toMatchTypeOf<ConfigPresetPreviewResponse>();
    expectTypeOf(applied).toMatchTypeOf<ConfigPresetApplyResponse>();
    expectTypeOf(exported).toMatchTypeOf<ConfigProfileExportResponse>();
    expectTypeOf(importPreview).toMatchTypeOf<ConfigProfileImportPreviewResponse>();
    expectTypeOf(importApply).toMatchTypeOf<ConfigProfileImportApplyResponse>();
  });

  it('rejects snake_case payloads, missing required keys, and generated aliases', () => {
    const snakeChange = {
      key: 'GENERATION_BACKEND',
      from_value: '',
      to: 'litellm',
    };
    const snakeList = {
      recommended_preset_id: 'local-first',
      detection: {
        ollama_healthy: true,
        model_pack_present: false,
        cloud_ready: false,
      },
      presets: [] as OpenApiItem[],
    };
    const undefinedRecommended = {
      recommendedPresetId: undefined,
      detection,
      presets: [] as ConfigPresetItem[],
    };
    expectTypeOf(snakeChange).toMatchTypeOf<OpenApiChange>();
    expectTypeOf(snakeChange).not.toMatchTypeOf<ConfigProfileChange>();
    expectTypeOf(snakeList).toMatchTypeOf<OpenApiList>();
    expectTypeOf(snakeList).not.toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf(undefinedRecommended).not.toMatchTypeOf<ConfigPresetListResponse>();
    expectTypeOf<ConfigProfileChange>().not.toMatchTypeOf<OpenApiChange>();
    expectTypeOf<OpenApiChange>().not.toMatchTypeOf<ConfigProfileChange>();
    expectTypeOf<ConfigPresetListResponse>().not.toMatchTypeOf<OpenApiList>();
    expectTypeOf<null>().toMatchTypeOf<ConfigPresetListResponse['recommendedPresetId']>();
    expectTypeOf<undefined>().not.toMatchTypeOf<ConfigPresetListResponse['recommendedPresetId']>();
  });
});
