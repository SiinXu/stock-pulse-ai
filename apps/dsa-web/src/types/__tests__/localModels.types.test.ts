// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as LocalModels from '../localModels';
import type {
  ImportedLocalModelMetadata,
  LocalModelCatalogEntry,
  LocalModelCatalogResponse,
  LocalModelConfiguration,
  LocalModelMutationResponse,
  LocalModelPullAccepted,
  LocalModelRuntimeState,
  LocalModelRuntimeStatus,
  ModelPackImportAccepted,
} from '../localModels';
import type { TaskLifecycleStatus } from '../analysis';

type OpenApiCatalog = components['schemas']['LocalModelCatalogResponse'];
type OpenApiEntry = components['schemas']['LocalModelCatalogEntry'];
type OpenApiConfig = components['schemas']['LocalModelConfigurationResponse'];
type OpenApiRuntime = components['schemas']['LocalModelRuntimeResponse'];
type OpenApiMutation = components['schemas']['LocalModelMutationResponse'];
type OpenApiUnregister = components['schemas']['LocalModelUnregistrationResponse'];
type OpenApiPullAccepted = components['schemas']['LocalModelPullAccepted'];
type OpenApiPullStatus = components['schemas']['LocalModelPullStatus'];
type OpenApiPackAccepted = components['schemas']['ModelPackImportAccepted'];
type OpenApiPackStatus = components['schemas']['ModelPackImportStatus'];

type OpenApiCatalogOp = operations['get_llm_local_model_catalog_api_v1_system_config_llm_local_models_get'];
type OpenApiRuntimeOp = operations['get_local_model_runtime_api_v1_local_models_runtime_get'];
type OpenApiConfigOp = operations['get_local_model_configuration_api_v1_local_models_configuration_get'];
type OpenApiPullOp = operations['start_local_model_pull_api_v1_local_models_pulls_post'];
type OpenApiPullStatusOp = operations['get_local_model_pull_api_v1_local_models_pulls__task_id__get'];
type OpenApiAssignOp = operations['assign_local_model_api_v1_local_models_assignments_post'];
type OpenApiDesktopActivateOp = operations['activate_desktop_local_model_api_v1_local_models_desktop_activations_post'];
type OpenApiDeleteOp = operations['delete_local_model_api_v1_local_models_models_delete'];
type OpenApiUnregisterOp = operations['unregister_local_model_api_v1_local_models_registrations_delete'];
type OpenApiRestoreOp = operations['restore_local_model_registration_api_v1_local_models_registrations_post'];
type OpenApiFinalizeOp = operations['finalize_local_model_unregistration_api_v1_local_models_registration_recoveries_finalize_post'];
type OpenApiPackImportOp = operations['import_model_pack_api_v1_model_packs_import_post'];
type OpenApiPackStatusOp = operations['get_model_pack_import_api_v1_model_packs_imports__task_id__get'];
type OpenApiPackActivateOp = operations['activate_desktop_model_pack_api_v1_model_packs_desktop_activations_post'];

type OpenApiCatalogPathGet = paths['/api/v1/system/config/llm/local-models']['get'];
type OpenApiRuntimePathGet = paths['/api/v1/local-models/runtime']['get'];
type OpenApiConfigPathGet = paths['/api/v1/local-models/configuration']['get'];
type OpenApiPullPathPost = paths['/api/v1/local-models/pulls']['post'];
type OpenApiPullStatusPathGet = paths['/api/v1/local-models/pulls/{task_id}']['get'];
type OpenApiAssignPathPost = paths['/api/v1/local-models/assignments']['post'];
type OpenApiDesktopActivatePathPost = paths['/api/v1/local-models/desktop-activations']['post'];
type OpenApiDeletePathDelete = paths['/api/v1/local-models/models']['delete'];
type OpenApiUnregisterPathDelete = paths['/api/v1/local-models/registrations']['delete'];
type OpenApiRestorePathPost = paths['/api/v1/local-models/registrations']['post'];
type OpenApiFinalizePathPost = paths['/api/v1/local-models/registration-recoveries/finalize']['post'];
type OpenApiPackImportPathPost = paths['/api/v1/model-packs/import']['post'];
type OpenApiPackStatusPathGet = paths['/api/v1/model-packs/imports/{task_id}']['get'];
type OpenApiPackActivatePathPost = paths['/api/v1/model-packs/desktop-activations']['post'];

type OpenApiCatalogGet200 = OpenApiCatalogOp['responses']['200']['content']['application/json'];
type OpenApiRuntimeGet200 = OpenApiRuntimeOp['responses']['200']['content']['application/json'];
type OpenApiConfigGet200 = OpenApiConfigOp['responses']['200']['content']['application/json'];
type OpenApiPullPost202 = OpenApiPullOp['responses']['202']['content']['application/json'];
type OpenApiPullStatusGet200 = OpenApiPullStatusOp['responses']['200']['content']['application/json'];
type OpenApiAssignPost200 = OpenApiAssignOp['responses']['200']['content']['application/json'];
type OpenApiDesktopActivatePost200 = OpenApiDesktopActivateOp['responses']['200']['content']['application/json'];
type OpenApiDelete200 = OpenApiDeleteOp['responses']['200']['content']['application/json'];
type OpenApiUnregisterDelete200 = OpenApiUnregisterOp['responses']['200']['content']['application/json'];
type OpenApiRestorePost200 = OpenApiRestoreOp['responses']['200']['content']['application/json'];
type OpenApiFinalizePost200 = OpenApiFinalizeOp['responses']['200']['content']['application/json'];
type OpenApiPackImportPost202 = OpenApiPackImportOp['responses']['202']['content']['application/json'];
type OpenApiPackStatusGet200 = OpenApiPackStatusOp['responses']['200']['content']['application/json'];
type OpenApiPackActivatePost200 = OpenApiPackActivateOp['responses']['200']['content']['application/json'];

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

type _FourteenComponents = _Assert<
  (
    | 'LocalModelCatalogResponse'
    | 'LocalModelCatalogEntry'
    | 'LocalModelCatalogText'
    | 'LocalModelConfigurationResponse'
    | 'LocalModelRuntimeResponse'
    | 'LocalModelMutationResponse'
    | 'LocalModelUnregistrationResponse'
    | 'LocalModelPullAccepted'
    | 'LocalModelPullResult'
    | 'LocalModelPullStatus'
    | 'ImportedLocalModelMetadata'
    | 'ModelPackImportAccepted'
    | 'ModelPackImportResult'
    | 'ModelPackImportStatus'
  ) extends keyof components['schemas'] ? true : false
>;

type _Catalog200IsCatalog = _Assert<OpenApiCatalogGet200 extends OpenApiCatalog ? true : false>;
type _CatalogIsCatalog200 = _Assert<OpenApiCatalog extends OpenApiCatalogGet200 ? true : false>;
type _CatalogOpIsPath = _Assert<OpenApiCatalogOp extends OpenApiCatalogPathGet ? true : false>;
type _PathIsCatalogOp = _Assert<OpenApiCatalogPathGet extends OpenApiCatalogOp ? true : false>;
type _CatalogGetNeverRequestBody = _Assert<OpenApiCatalogOp extends { requestBody?: never } ? true : false>;
type _CatalogHas200 = _Assert<200 extends keyof OpenApiCatalogOp['responses'] ? true : false>;
type _CatalogLacks201 = _Assert<201 extends keyof OpenApiCatalogOp['responses'] ? false : true>;
type _Runtime200IsRuntime = _Assert<OpenApiRuntimeGet200 extends OpenApiRuntime ? true : false>;
type _RuntimeIsRuntime200 = _Assert<OpenApiRuntime extends OpenApiRuntimeGet200 ? true : false>;
type _RuntimeOpIsPath = _Assert<OpenApiRuntimeOp extends OpenApiRuntimePathGet ? true : false>;
type _PathIsRuntimeOp = _Assert<OpenApiRuntimePathGet extends OpenApiRuntimeOp ? true : false>;
type _RuntimeGetNeverRequestBody = _Assert<OpenApiRuntimeOp extends { requestBody?: never } ? true : false>;
type _RuntimeHas200 = _Assert<200 extends keyof OpenApiRuntimeOp['responses'] ? true : false>;
type _RuntimeLacks201 = _Assert<201 extends keyof OpenApiRuntimeOp['responses'] ? false : true>;
type _Config200IsConfig = _Assert<OpenApiConfigGet200 extends OpenApiConfig ? true : false>;
type _ConfigIsConfig200 = _Assert<OpenApiConfig extends OpenApiConfigGet200 ? true : false>;
type _ConfigOpIsPath = _Assert<OpenApiConfigOp extends OpenApiConfigPathGet ? true : false>;
type _PathIsConfigOp = _Assert<OpenApiConfigPathGet extends OpenApiConfigOp ? true : false>;
type _ConfigGetNeverRequestBody = _Assert<OpenApiConfigOp extends { requestBody?: never } ? true : false>;
type _ConfigHas200 = _Assert<200 extends keyof OpenApiConfigOp['responses'] ? true : false>;
type _ConfigLacks201 = _Assert<201 extends keyof OpenApiConfigOp['responses'] ? false : true>;
type _Pull202IsAccepted = _Assert<OpenApiPullPost202 extends OpenApiPullAccepted ? true : false>;
type _AcceptedIsPull202 = _Assert<OpenApiPullAccepted extends OpenApiPullPost202 ? true : false>;
type _PullOpIsPath = _Assert<OpenApiPullOp extends OpenApiPullPathPost ? true : false>;
type _PathIsPullOp = _Assert<OpenApiPullPathPost extends OpenApiPullOp ? true : false>;
type _PullHas202 = _Assert<202 extends keyof OpenApiPullOp['responses'] ? true : false>;
type _PullLacks200 = _Assert<200 extends keyof OpenApiPullOp['responses'] ? false : true>;
type _PullLacks201 = _Assert<201 extends keyof OpenApiPullOp['responses'] ? false : true>;
type _PullStatus200IsStatus = _Assert<OpenApiPullStatusGet200 extends OpenApiPullStatus ? true : false>;
type _StatusIsPullStatus200 = _Assert<OpenApiPullStatus extends OpenApiPullStatusGet200 ? true : false>;
type _PullStatusOpIsPath = _Assert<OpenApiPullStatusOp extends OpenApiPullStatusPathGet ? true : false>;
type _PathIsPullStatusOp = _Assert<OpenApiPullStatusPathGet extends OpenApiPullStatusOp ? true : false>;
type _PullStatusGetNeverRequestBody = _Assert<OpenApiPullStatusOp extends { requestBody?: never } ? true : false>;
type _Assign200IsMutation = _Assert<OpenApiAssignPost200 extends OpenApiMutation ? true : false>;
type _MutationIsAssign200 = _Assert<OpenApiMutation extends OpenApiAssignPost200 ? true : false>;
type _AssignOpIsPath = _Assert<OpenApiAssignOp extends OpenApiAssignPathPost ? true : false>;
type _PathIsAssignOp = _Assert<OpenApiAssignPathPost extends OpenApiAssignOp ? true : false>;
type _DesktopActivate200IsMutation = _Assert<OpenApiDesktopActivatePost200 extends OpenApiMutation ? true : false>;
type _MutationIsDesktopActivate200 = _Assert<OpenApiMutation extends OpenApiDesktopActivatePost200 ? true : false>;
type _DesktopActivateOpIsPath = _Assert<OpenApiDesktopActivateOp extends OpenApiDesktopActivatePathPost ? true : false>;
type _PathIsDesktopActivateOp = _Assert<OpenApiDesktopActivatePathPost extends OpenApiDesktopActivateOp ? true : false>;
type _Delete200IsMutation = _Assert<OpenApiDelete200 extends OpenApiMutation ? true : false>;
type _MutationIsDelete200 = _Assert<OpenApiMutation extends OpenApiDelete200 ? true : false>;
type _DeleteOpIsPath = _Assert<OpenApiDeleteOp extends OpenApiDeletePathDelete ? true : false>;
type _PathIsDeleteOp = _Assert<OpenApiDeletePathDelete extends OpenApiDeleteOp ? true : false>;
type _Unregister200IsUnregister = _Assert<OpenApiUnregisterDelete200 extends OpenApiUnregister ? true : false>;
type _UnregisterIsUnregister200 = _Assert<OpenApiUnregister extends OpenApiUnregisterDelete200 ? true : false>;
type _UnregisterOpIsPath = _Assert<OpenApiUnregisterOp extends OpenApiUnregisterPathDelete ? true : false>;
type _PathIsUnregisterOp = _Assert<OpenApiUnregisterPathDelete extends OpenApiUnregisterOp ? true : false>;
type _Restore200IsMutation = _Assert<OpenApiRestorePost200 extends OpenApiMutation ? true : false>;
type _MutationIsRestore200 = _Assert<OpenApiMutation extends OpenApiRestorePost200 ? true : false>;
type _RestoreOpIsPath = _Assert<OpenApiRestoreOp extends OpenApiRestorePathPost ? true : false>;
type _PathIsRestoreOp = _Assert<OpenApiRestorePathPost extends OpenApiRestoreOp ? true : false>;
type _Finalize200IsMutation = _Assert<OpenApiFinalizePost200 extends OpenApiMutation ? true : false>;
type _MutationIsFinalize200 = _Assert<OpenApiMutation extends OpenApiFinalizePost200 ? true : false>;
type _FinalizeOpIsPath = _Assert<OpenApiFinalizeOp extends OpenApiFinalizePathPost ? true : false>;
type _PathIsFinalizeOp = _Assert<OpenApiFinalizePathPost extends OpenApiFinalizeOp ? true : false>;
type _PackImport202IsAccepted = _Assert<OpenApiPackImportPost202 extends OpenApiPackAccepted ? true : false>;
type _AcceptedIsPackImport202 = _Assert<OpenApiPackAccepted extends OpenApiPackImportPost202 ? true : false>;
type _PackImportOpIsPath = _Assert<OpenApiPackImportOp extends OpenApiPackImportPathPost ? true : false>;
type _PathIsPackImportOp = _Assert<OpenApiPackImportPathPost extends OpenApiPackImportOp ? true : false>;
type _PackImportHas202 = _Assert<202 extends keyof OpenApiPackImportOp['responses'] ? true : false>;
type _PackImportLacks200 = _Assert<200 extends keyof OpenApiPackImportOp['responses'] ? false : true>;
type _PackImportLacks201 = _Assert<201 extends keyof OpenApiPackImportOp['responses'] ? false : true>;
type _PackStatus200IsStatus = _Assert<OpenApiPackStatusGet200 extends OpenApiPackStatus ? true : false>;
type _StatusIsPackStatus200 = _Assert<OpenApiPackStatus extends OpenApiPackStatusGet200 ? true : false>;
type _PackStatusOpIsPath = _Assert<OpenApiPackStatusOp extends OpenApiPackStatusPathGet ? true : false>;
type _PathIsPackStatusOp = _Assert<OpenApiPackStatusPathGet extends OpenApiPackStatusOp ? true : false>;
type _PackStatusGetNeverRequestBody = _Assert<OpenApiPackStatusOp extends { requestBody?: never } ? true : false>;
type _PackActivate200IsMutation = _Assert<OpenApiPackActivatePost200 extends OpenApiMutation ? true : false>;
type _MutationIsPackActivate200 = _Assert<OpenApiMutation extends OpenApiPackActivatePost200 ? true : false>;
type _PackActivateOpIsPath = _Assert<OpenApiPackActivateOp extends OpenApiPackActivatePathPost ? true : false>;
type _PathIsPackActivateOp = _Assert<OpenApiPackActivatePathPost extends OpenApiPackActivateOp ? true : false>;

type _PublicRuntimeNotPath200 = _Assert<LocalModelRuntimeState extends OpenApiRuntimeGet200 ? false : true>;
type _Path200NotPublicRuntime = _Assert<OpenApiRuntimeGet200 extends LocalModelRuntimeState ? false : true>;

type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof LocalModelCatalogResponse ? true : false>;
type _UiHasCapabilitySummary = _Assert<'capabilitySummary' extends keyof LocalModelCatalogEntry ? true : false>;
type _UiHasRecommendedRamGb = _Assert<'recommendedRamGb' extends keyof LocalModelCatalogEntry ? true : false>;
type _UiHasConfigVersion = _Assert<'configVersion' extends keyof LocalModelConfiguration ? true : false>;
type _UiHasTaskId = _Assert<'taskId' extends keyof LocalModelPullAccepted ? true : false>;
type _UiHasRecoveryToken = _Assert<'recoveryToken' extends keyof LocalModels.LocalModelUnregistrationResponse ? true : false>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof LocalModelCatalogResponse ? false : true>;
type _UiLacksCapabilitySummarySnake = _Assert<'capability_summary' extends keyof LocalModelCatalogEntry ? false : true>;
type _UiLacksRecommendedRamGbSnake = _Assert<'recommended_ram_gb' extends keyof LocalModelCatalogEntry ? false : true>;
type _UiLacksConfigVersionSnake = _Assert<'config_version' extends keyof LocalModelConfiguration ? false : true>;
type _UiLacksTaskIdSnake = _Assert<'task_id' extends keyof LocalModelPullAccepted ? false : true>;
type _UiLacksRecoveryTokenSnake = _Assert<'recovery_token' extends keyof LocalModels.LocalModelUnregistrationResponse ? false : true>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiCatalog ? true : false>;
type _GeneratedHasCapabilitySummarySnake = _Assert<'capability_summary' extends keyof OpenApiEntry ? true : false>;
type _GeneratedHasRecommendedRamGbSnake = _Assert<'recommended_ram_gb' extends keyof OpenApiEntry ? true : false>;
type _GeneratedHasConfigVersionSnake = _Assert<'config_version' extends keyof OpenApiConfig ? true : false>;
type _GeneratedHasTaskIdSnake = _Assert<'task_id' extends keyof OpenApiPullAccepted ? true : false>;
type _GeneratedHasRecoveryTokenSnake = _Assert<'recovery_token' extends keyof OpenApiUnregister ? true : false>;
type _GeneratedLacksSchemaVersionCamel = _Assert<'schemaVersion' extends keyof OpenApiCatalog ? false : true>;
type _GeneratedLacksCapabilitySummaryCamel = _Assert<'capabilitySummary' extends keyof OpenApiEntry ? false : true>;
type _GeneratedLacksRecommendedRamGbCamel = _Assert<'recommendedRamGb' extends keyof OpenApiEntry ? false : true>;
type _GeneratedLacksConfigVersionCamel = _Assert<'configVersion' extends keyof OpenApiConfig ? false : true>;
type _GeneratedLacksTaskIdCamel = _Assert<'taskId' extends keyof OpenApiPullAccepted ? false : true>;
type _GeneratedLacksRecoveryTokenCamel = _Assert<'recoveryToken' extends keyof OpenApiUnregister ? false : true>;

type _UiRegisteredModelsRequired = _Assert<IsOptional<LocalModelConfiguration, 'registeredModels'> extends false ? true : false>;
type _GeneratedRegisteredModelsOptional = _Assert<IsOptional<OpenApiConfig, 'registered_models'>>;
type _NaiveRegisteredModelsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiConfig>, 'registeredModels'>>;
type _UiUpdatedKeysRequired = _Assert<IsOptional<LocalModelMutationResponse, 'updatedKeys'> extends false ? true : false>;
type _UiWarningsRequired = _Assert<IsOptional<LocalModelMutationResponse, 'warnings'> extends false ? true : false>;
type _GeneratedUpdatedKeysOptional = _Assert<IsOptional<OpenApiMutation, 'updated_keys'>>;
type _GeneratedWarningsOptional = _Assert<IsOptional<OpenApiMutation, 'warnings'>>;
type _NaiveUpdatedKeysOptional = _Assert<IsOptional<CamelizeKeys<OpenApiMutation>, 'updatedKeys'>>;
type _NaiveWarningsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiMutation>, 'warnings'>>;
type _UiInstalledModelsRequired = _Assert<IsOptional<LocalModelRuntimeState, 'installedModels'> extends false ? true : false>;
type _UiLocalInstallPlatformRequired = _Assert<
  IsOptional<LocalModelRuntimeState, 'localInstallPlatform'> extends false ? true : false
>;
type _GeneratedInstalledModelsOptional = _Assert<IsOptional<OpenApiRuntime, 'installed_models'>>;
type _GeneratedLocalInstallPlatformOptional = _Assert<IsOptional<OpenApiRuntime, 'local_install_platform'>>;
type _UiHasStopped = _Assert<'stopped' extends LocalModelRuntimeStatus ? true : false>;
type _UiHasStarting = _Assert<'starting' extends LocalModelRuntimeStatus ? true : false>;
type _UiHasNotInstalled = _Assert<'not-installed' extends LocalModelRuntimeStatus ? true : false>;
type _GeneratedLacksStopped = _Assert<'stopped' extends OpenApiRuntime['status'] ? false : true>;
type _GeneratedLacksStarting = _Assert<'starting' extends OpenApiRuntime['status'] ? false : true>;
type _GeneratedLacksNotInstalled = _Assert<'not-installed' extends OpenApiRuntime['status'] ? false : true>;
type _UiHasTotalMemoryGb = _Assert<'totalMemoryGb' extends keyof LocalModelRuntimeState ? true : false>;
type _NaiveLacksTotalMemoryGb = _Assert<'totalMemoryGb' extends keyof CamelizeKeys<OpenApiRuntime> ? false : true>;
type _GeneratedLacksTotalMemoryGb = _Assert<'totalMemoryGb' extends keyof OpenApiRuntime ? false : true>;
type _GeneratedLacksTotalMemoryGbSnake = _Assert<'total_memory_gb' extends keyof OpenApiRuntime ? false : true>;
type _UiPackStatusAccepted = _Assert<ModelPackImportAccepted['status'] extends 'accepted' ? true : false>;
type _AcceptedIsUiPackStatus = _Assert<'accepted' extends ModelPackImportAccepted['status'] ? true : false>;
type _NaivePackStatusIsString = _Assert<CamelizeKeys<OpenApiPackAccepted>['status'] extends string ? true : false>;
type _UiPullStatusIsTaskLifecycle = _Assert<
  LocalModelPullAccepted['status'] extends TaskLifecycleStatus ? true : false
>;
type _TaskLifecycleIsUiPullStatus = _Assert<
  TaskLifecycleStatus extends LocalModelPullAccepted['status'] ? true : false
>;

type PartialConfig = { configVersion: string; primaryModel: string; agentModel: string };
type _PartialConfigRejected = _Assert<PartialConfig extends LocalModelConfiguration ? false : true>;
type _NaivePartialConfigAssignable = _Assert<PartialConfig extends CamelizeKeys<OpenApiConfig> ? true : false>;

type PartialMutation = {
  configVersion: string;
  registeredModels: string[];
  primaryModel: string;
  agentModel: string;
  success: boolean;
  modelId: string;
  selectedPrimary: boolean;
  selectedAgent: boolean;
  deleted: boolean;
  appliedCount: number;
  skippedMaskedCount: number;
  reloadTriggered: boolean;
};
type _PartialMutationRejected = _Assert<PartialMutation extends LocalModelMutationResponse ? false : true>;
type _NaivePartialMutationAssignable = _Assert<PartialMutation extends CamelizeKeys<OpenApiMutation> ? true : false>;

type QueuedPack = {
  status: 'queued';
  taskId: string;
  message: string;
  messageCode: string;
};
type _QueuedPackRejected = _Assert<QueuedPack extends ModelPackImportAccepted ? false : true>;
type _NaiveQueuedPackAssignable = _Assert<QueuedPack extends CamelizeKeys<OpenApiPackAccepted> ? true : false>;

type _CompileTimePins = [
  _FourteenComponents,
  _Catalog200IsCatalog,
  _CatalogIsCatalog200,
  _CatalogOpIsPath,
  _PathIsCatalogOp,
  _CatalogGetNeverRequestBody,
  _CatalogHas200,
  _CatalogLacks201,
  _Runtime200IsRuntime,
  _RuntimeIsRuntime200,
  _RuntimeOpIsPath,
  _PathIsRuntimeOp,
  _RuntimeGetNeverRequestBody,
  _RuntimeHas200,
  _RuntimeLacks201,
  _Config200IsConfig,
  _ConfigIsConfig200,
  _ConfigOpIsPath,
  _PathIsConfigOp,
  _ConfigGetNeverRequestBody,
  _ConfigHas200,
  _ConfigLacks201,
  _Pull202IsAccepted,
  _AcceptedIsPull202,
  _PullOpIsPath,
  _PathIsPullOp,
  _PullHas202,
  _PullLacks200,
  _PullLacks201,
  _PullStatus200IsStatus,
  _StatusIsPullStatus200,
  _PullStatusOpIsPath,
  _PathIsPullStatusOp,
  _PullStatusGetNeverRequestBody,
  _Assign200IsMutation,
  _MutationIsAssign200,
  _AssignOpIsPath,
  _PathIsAssignOp,
  _DesktopActivate200IsMutation,
  _MutationIsDesktopActivate200,
  _DesktopActivateOpIsPath,
  _PathIsDesktopActivateOp,
  _Delete200IsMutation,
  _MutationIsDelete200,
  _DeleteOpIsPath,
  _PathIsDeleteOp,
  _Unregister200IsUnregister,
  _UnregisterIsUnregister200,
  _UnregisterOpIsPath,
  _PathIsUnregisterOp,
  _Restore200IsMutation,
  _MutationIsRestore200,
  _RestoreOpIsPath,
  _PathIsRestoreOp,
  _Finalize200IsMutation,
  _MutationIsFinalize200,
  _FinalizeOpIsPath,
  _PathIsFinalizeOp,
  _PackImport202IsAccepted,
  _AcceptedIsPackImport202,
  _PackImportOpIsPath,
  _PathIsPackImportOp,
  _PackImportHas202,
  _PackImportLacks200,
  _PackImportLacks201,
  _PackStatus200IsStatus,
  _StatusIsPackStatus200,
  _PackStatusOpIsPath,
  _PathIsPackStatusOp,
  _PackStatusGetNeverRequestBody,
  _PackActivate200IsMutation,
  _MutationIsPackActivate200,
  _PackActivateOpIsPath,
  _PathIsPackActivateOp,
  _PublicRuntimeNotPath200,
  _Path200NotPublicRuntime,
  _UiHasSchemaVersion,
  _UiHasCapabilitySummary,
  _UiHasRecommendedRamGb,
  _UiHasConfigVersion,
  _UiHasTaskId,
  _UiHasRecoveryToken,
  _UiLacksSchemaVersionSnake,
  _UiLacksCapabilitySummarySnake,
  _UiLacksRecommendedRamGbSnake,
  _UiLacksConfigVersionSnake,
  _UiLacksTaskIdSnake,
  _UiLacksRecoveryTokenSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasCapabilitySummarySnake,
  _GeneratedHasRecommendedRamGbSnake,
  _GeneratedHasConfigVersionSnake,
  _GeneratedHasTaskIdSnake,
  _GeneratedHasRecoveryTokenSnake,
  _GeneratedLacksSchemaVersionCamel,
  _GeneratedLacksCapabilitySummaryCamel,
  _GeneratedLacksRecommendedRamGbCamel,
  _GeneratedLacksConfigVersionCamel,
  _GeneratedLacksTaskIdCamel,
  _GeneratedLacksRecoveryTokenCamel,
  _UiRegisteredModelsRequired,
  _GeneratedRegisteredModelsOptional,
  _NaiveRegisteredModelsOptional,
  _UiUpdatedKeysRequired,
  _UiWarningsRequired,
  _GeneratedUpdatedKeysOptional,
  _GeneratedWarningsOptional,
  _NaiveUpdatedKeysOptional,
  _NaiveWarningsOptional,
  _UiInstalledModelsRequired,
  _UiLocalInstallPlatformRequired,
  _GeneratedInstalledModelsOptional,
  _GeneratedLocalInstallPlatformOptional,
  _UiHasStopped,
  _UiHasStarting,
  _UiHasNotInstalled,
  _GeneratedLacksStopped,
  _GeneratedLacksStarting,
  _GeneratedLacksNotInstalled,
  _UiHasTotalMemoryGb,
  _NaiveLacksTotalMemoryGb,
  _GeneratedLacksTotalMemoryGb,
  _GeneratedLacksTotalMemoryGbSnake,
  _UiPackStatusAccepted,
  _AcceptedIsUiPackStatus,
  _NaivePackStatusIsString,
  _UiPullStatusIsTaskLifecycle,
  _TaskLifecycleIsUiPullStatus,
  _PartialConfigRejected,
  _NaivePartialConfigAssignable,
  _PartialMutationRejected,
  _NaivePartialMutationAssignable,
  _QueuedPackRejected,
  _NaiveQueuedPackAssignable,
];

const catalogBase = {
  id: 'qwen3-4b',
  section: 'general' as const,
  displayName: { en: 'Qwen3 4B', zh: 'Qwen3 4B' },
  capabilitySummary: { en: 'Compact local reasoning model.', zh: '轻量本地推理模型。' },
  capabilities: ['general', 'reasoning'],
  q4: {
    quantization: 'Q4_K_M' as const,
    sizeBytes: 2_497_280_480,
    sourceKind: 'official_ollama' as const,
    sourceUrl: 'https://ollama.com/library/qwen3:4b',
    sourceRevision: 'sha256:test',
  },
  memoryTier: 'light' as const,
  recommendedRamGb: 8,
  license: {
    identifier: 'Apache-2.0',
    name: 'Apache License 2.0',
    evidenceUrl: 'https://example.test/license',
    redistribution: 'allowed_with_notice' as const,
    standaloneLicenseFile: true,
  },
  upstream: { primaryUrl: 'https://ollama.com/library/qwen3:4b', revision: 'test' },
  install: {
    method: 'ollama_pull' as const,
    status: 'available' as const,
    ollamaTag: 'qwen3:4b',
    downloadUrl: 'https://ollama.com/library/qwen3:4b',
    hostedByStockpulse: false,
  },
  desktop: { recommended: true, role: 'lightweight' as const, guidanceEn: '8 GB RAM' },
};

// @ts-expect-error futureCatalogFlag is not a public catalog field
const extraCatalog: LocalModelCatalogEntry = { ...catalogBase, futureCatalogFlag: true };

const runtimeBase = {
  runtime: 'ollama' as const,
  status: 'running' as const,
  installedModels: [] as string[],
  manualPullSupported: false,
  localInstallPlatform: 'macos' as const,
  configuration: {
    configVersion: 'config-1',
    registeredModels: [] as string[],
    primaryModel: 'openai/gpt-5',
    agentModel: '',
  },
};

// @ts-expect-error futureRuntimeFlag is not a public runtime field
const extraRuntime: LocalModelRuntimeState = { ...runtimeBase, futureRuntimeFlag: true };

const extraImported: ImportedLocalModelMetadata = {
  modelId: 'pack-1',
  displayName: 'Pack',
  minimumMemoryGb: 8,
  licenseId: 'Apache-2.0',
  // @ts-expect-error futureLicenseFlag is not a public imported-metadata field
  futureLicenseFlag: true,
};

const pullAcceptedBase = {
  taskId: 'pull-1',
  traceId: 'trace-1',
  status: 'pending' as const,
  modelId: 'qwen3-4b',
};

// @ts-expect-error snake task_id is not a public pull-accepted field
const snakePull: LocalModelPullAccepted = { ...pullAcceptedBase, task_id: 'pull-1' };

void extraCatalog;
void extraRuntime;
void extraImported;
void snakePull;

describe('localModels OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...LocalModels }).toEqual({});
    expect(Object.keys(LocalModels)).toEqual([]);
    expect(Object.getOwnPropertyNames(LocalModels)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200/202 not 201', () => {
    expectTypeOf<OpenApiCatalogGet200>().toEqualTypeOf<OpenApiCatalog>();
    expectTypeOf<OpenApiRuntimeGet200>().toEqualTypeOf<OpenApiRuntime>();
    expectTypeOf<OpenApiConfigGet200>().toEqualTypeOf<OpenApiConfig>();
    expectTypeOf<OpenApiPullPost202>().toEqualTypeOf<OpenApiPullAccepted>();
    expectTypeOf<OpenApiPullStatusGet200>().toEqualTypeOf<OpenApiPullStatus>();
    expectTypeOf<OpenApiAssignPost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiDesktopActivatePost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiDelete200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiUnregisterDelete200>().toEqualTypeOf<OpenApiUnregister>();
    expectTypeOf<OpenApiRestorePost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiFinalizePost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiPackImportPost202>().toEqualTypeOf<OpenApiPackAccepted>();
    expectTypeOf<OpenApiPackStatusGet200>().toEqualTypeOf<OpenApiPackStatus>();
    expectTypeOf<OpenApiPackActivatePost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiCatalogOp>().toEqualTypeOf<OpenApiCatalogPathGet>();
    expectTypeOf<OpenApiRuntimeOp>().toEqualTypeOf<OpenApiRuntimePathGet>();
    expectTypeOf<OpenApiConfigOp>().toEqualTypeOf<OpenApiConfigPathGet>();
    expectTypeOf<OpenApiPullOp>().toEqualTypeOf<OpenApiPullPathPost>();
    expectTypeOf<OpenApiPullStatusOp>().toEqualTypeOf<OpenApiPullStatusPathGet>();
    expectTypeOf<OpenApiAssignOp>().toEqualTypeOf<OpenApiAssignPathPost>();
    expectTypeOf<OpenApiDesktopActivateOp>().toEqualTypeOf<OpenApiDesktopActivatePathPost>();
    expectTypeOf<OpenApiDeleteOp>().toEqualTypeOf<OpenApiDeletePathDelete>();
    expectTypeOf<OpenApiUnregisterOp>().toEqualTypeOf<OpenApiUnregisterPathDelete>();
    expectTypeOf<OpenApiRestoreOp>().toEqualTypeOf<OpenApiRestorePathPost>();
    expectTypeOf<OpenApiFinalizeOp>().toEqualTypeOf<OpenApiFinalizePathPost>();
    expectTypeOf<OpenApiPackImportOp>().toEqualTypeOf<OpenApiPackImportPathPost>();
    expectTypeOf<OpenApiPackStatusOp>().toEqualTypeOf<OpenApiPackStatusPathGet>();
    expectTypeOf<OpenApiPackActivateOp>().toEqualTypeOf<OpenApiPackActivatePathPost>();
    type CatalogNeverBody = OpenApiCatalogOp extends { requestBody?: never } ? true : false;
    type RuntimeNeverBody = OpenApiRuntimeOp extends { requestBody?: never } ? true : false;
    type ConfigNeverBody = OpenApiConfigOp extends { requestBody?: never } ? true : false;
    type PullStatusNeverBody = OpenApiPullStatusOp extends { requestBody?: never } ? true : false;
    type PackStatusNeverBody = OpenApiPackStatusOp extends { requestBody?: never } ? true : false;
    type CatalogHas201 = 201 extends keyof OpenApiCatalogOp['responses'] ? true : false;
    type RuntimeHas201 = 201 extends keyof OpenApiRuntimeOp['responses'] ? true : false;
    type ConfigHas201 = 201 extends keyof OpenApiConfigOp['responses'] ? true : false;
    type PullHas200 = 200 extends keyof OpenApiPullOp['responses'] ? true : false;
    type PullHas201 = 201 extends keyof OpenApiPullOp['responses'] ? true : false;
    type PackImportHas200 = 200 extends keyof OpenApiPackImportOp['responses'] ? true : false;
    type PackImportHas201 = 201 extends keyof OpenApiPackImportOp['responses'] ? true : false;
    expectTypeOf<CatalogNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<RuntimeNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ConfigNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<PullStatusNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<PackStatusNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<CatalogHas201>().toEqualTypeOf<false>();
    expectTypeOf<RuntimeHas201>().toEqualTypeOf<false>();
    expectTypeOf<ConfigHas201>().toEqualTypeOf<false>();
    expectTypeOf<PullHas200>().toEqualTypeOf<false>();
    expectTypeOf<PullHas201>().toEqualTypeOf<false>();
    expectTypeOf<PackImportHas200>().toEqualTypeOf<false>();
    expectTypeOf<PackImportHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public LocalModelRuntimeState equals runtime path 200 JSON', () => {
    type PublicExtendsPath = LocalModelRuntimeState extends OpenApiRuntimeGet200 ? true : false;
    type PathExtendsPublic = OpenApiRuntimeGet200 extends LocalModelRuntimeState ? true : false;
    expectTypeOf<PublicExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublic>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof LocalModelCatalogResponse>().not.toMatchTypeOf<'schema_version'>();
    expectTypeOf<keyof LocalModelCatalogEntry>().not.toMatchTypeOf<'capability_summary' | 'recommended_ram_gb'>();
    expectTypeOf<keyof LocalModelConfiguration>().not.toMatchTypeOf<'config_version'>();
    expectTypeOf<keyof LocalModelPullAccepted>().not.toMatchTypeOf<'task_id'>();
    expectTypeOf<keyof LocalModels.LocalModelUnregistrationResponse>().not.toMatchTypeOf<'recovery_token'>();
    expectTypeOf<keyof OpenApiCatalog>().not.toMatchTypeOf<'schemaVersion'>();
    expectTypeOf<keyof OpenApiEntry>().not.toMatchTypeOf<'capabilitySummary' | 'recommendedRamGb'>();
    expectTypeOf<keyof OpenApiConfig>().not.toMatchTypeOf<'configVersion'>();
    expectTypeOf<keyof OpenApiPullAccepted>().not.toMatchTypeOf<'taskId'>();
    expectTypeOf<keyof OpenApiUnregister>().not.toMatchTypeOf<'recoveryToken'>();
  });

  it('keeps UI configuration registeredModels required while naive CamelizeKeys leaves them optional', () => {
    const omittedRegistered = { configVersion: 'config-1', primaryModel: 'openai/gpt-5', agentModel: '' };
    expectTypeOf(omittedRegistered).not.toMatchTypeOf<LocalModelConfiguration>();
    expectTypeOf(omittedRegistered).toMatchTypeOf<CamelizeKeys<OpenApiConfig>>();
    type UiOptional = IsOptional<LocalModelConfiguration, 'registeredModels'>;
    type NaiveOptional = IsOptional<CamelizeKeys<OpenApiConfig>, 'registeredModels'>;
    expectTypeOf<UiOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI mutation updatedKeys and warnings required while naive CamelizeKeys leaves them optional', () => {
    const omittedArrays = {
      configVersion: 'config-1',
      registeredModels: [] as string[],
      primaryModel: 'openai/gpt-5',
      agentModel: '',
      success: true,
      modelId: 'qwen3-4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      appliedCount: 0,
      skippedMaskedCount: 0,
      reloadTriggered: false,
    };
    expectTypeOf(omittedArrays).not.toMatchTypeOf<LocalModelMutationResponse>();
    expectTypeOf(omittedArrays).toMatchTypeOf<CamelizeKeys<OpenApiMutation>>();
    type UiUpdatedOptional = IsOptional<LocalModelMutationResponse, 'updatedKeys'>;
    type UiWarningsOptional = IsOptional<LocalModelMutationResponse, 'warnings'>;
    type NaiveUpdatedOptional = IsOptional<CamelizeKeys<OpenApiMutation>, 'updatedKeys'>;
    type NaiveWarningsOptional = IsOptional<CamelizeKeys<OpenApiMutation>, 'warnings'>;
    expectTypeOf<UiUpdatedOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiWarningsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveUpdatedOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveWarningsOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI runtime status wider than generated and accepts desktop extras', () => {
    expectTypeOf<'stopped'>().toMatchTypeOf<LocalModelRuntimeStatus>();
    expectTypeOf<'starting'>().toMatchTypeOf<LocalModelRuntimeStatus>();
    expectTypeOf<'not-installed'>().toMatchTypeOf<LocalModelRuntimeStatus>();
    type GeneratedHasStopped = 'stopped' extends OpenApiRuntime['status'] ? true : false;
    type GeneratedHasStarting = 'starting' extends OpenApiRuntime['status'] ? true : false;
    type GeneratedHasNotInstalled = 'not-installed' extends OpenApiRuntime['status'] ? true : false;
    expectTypeOf<GeneratedHasStopped>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasStarting>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasNotInstalled>().toEqualTypeOf<false>();
    const stoppedRuntime: LocalModelRuntimeState = { ...runtimeBase, status: 'stopped' };
    const availableWithMemory: LocalModelRuntimeState = { ...runtimeBase, totalMemoryGb: 16 };
    expectTypeOf(stoppedRuntime).toMatchTypeOf<LocalModelRuntimeState>();
    expectTypeOf(availableWithMemory).toMatchTypeOf<LocalModelRuntimeState>();
    type NaiveHasMemory = 'totalMemoryGb' extends keyof CamelizeKeys<OpenApiRuntime> ? true : false;
    type NaiveHasStopped = 'stopped' extends CamelizeKeys<OpenApiRuntime>['status'] ? true : false;
    expectTypeOf<NaiveHasMemory>().toEqualTypeOf<false>();
    expectTypeOf<NaiveHasStopped>().toEqualTypeOf<false>();
  });

  it("keeps UI ModelPack status as the 'accepted' literal while naive CamelizeKeys is string", () => {
    const queuedPack = {
      status: 'queued' as const,
      taskId: 'pack-1',
      message: 'queued',
      messageCode: 'local_model.import.queued',
    };
    expectTypeOf(queuedPack).not.toMatchTypeOf<ModelPackImportAccepted>();
    expectTypeOf(queuedPack).toMatchTypeOf<CamelizeKeys<OpenApiPackAccepted>>();
    const acceptedPack = {
      status: 'accepted' as const,
      taskId: 'pack-1',
      message: 'accepted',
      messageCode: 'local_model.import.queued',
    };
    expectTypeOf(acceptedPack).toMatchTypeOf<ModelPackImportAccepted>();
  });

  it('keeps TaskLifecycleStatus identity on pull accepted status and does not re-export TaskStatusEnum', () => {
    expectTypeOf<'pending'>().toMatchTypeOf<LocalModelPullAccepted['status']>();
    expectTypeOf<LocalModelPullAccepted['status']>().toEqualTypeOf<TaskLifecycleStatus>();
    expectTypeOf(pullAcceptedBase).toMatchTypeOf<LocalModelPullAccepted>();
    type ExportedTaskStatusEnum = 'TaskStatusEnum' extends keyof typeof LocalModels ? true : false;
    expectTypeOf<ExportedTaskStatusEnum>().toEqualTypeOf<false>();
  });
});
