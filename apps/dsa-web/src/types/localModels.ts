// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { TaskLifecycleStatus } from './analysis';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiCatalog = components['schemas']['LocalModelCatalogResponse'];
type OpenApiEntry = components['schemas']['LocalModelCatalogEntry'];
type OpenApiText = components['schemas']['LocalModelCatalogText'];
type OpenApiConfig = components['schemas']['LocalModelConfigurationResponse'];
type OpenApiRuntime = components['schemas']['LocalModelRuntimeResponse'];
type OpenApiMutation = components['schemas']['LocalModelMutationResponse'];
type OpenApiUnregister = components['schemas']['LocalModelUnregistrationResponse'];
type OpenApiPullAccepted = components['schemas']['LocalModelPullAccepted'];
type OpenApiPullResult = components['schemas']['LocalModelPullResult'];
type OpenApiPullStatus = components['schemas']['LocalModelPullStatus'];
type OpenApiImported = components['schemas']['ImportedLocalModelMetadata'];
type OpenApiPackAccepted = components['schemas']['ModelPackImportAccepted'];
type OpenApiPackResult = components['schemas']['ModelPackImportResult'];
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

type _Assert<T extends true> = T;
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

type _OpenApiAnchors = [
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
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type LocalModelSection = 'general' | 'finance';
export type LocalModelMemoryTier = 'light' | 'standard' | 'high';
export type LocalModelInstallMethod = 'ollama_pull' | 'planned_ollama_package' | 'guided_import';
export type LocalModelInstallStatus = 'available' | 'conversion_required' | 'license_review_required';
export type LocalModelAssignment = 'auto' | 'primary' | 'agent';
export type LocalModelRuntimeStatus =
  | 'unknown'
  | 'running'
  | 'unavailable'
  | 'not-installed'
  | 'stopped'
  | 'starting'
  | 'error';

export type LocalizedCatalogText = CamelizeKeys<OpenApiText>;
export type ImportedLocalModelMetadata = CamelizeKeys<OpenApiImported>;

export type LocalModelCatalogEntry = CamelizeKeys<OpenApiEntry>;

export type LocalModelCatalogResponse = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiCatalog>, {
  models: LocalModelCatalogEntry[];
}>>;

export type LocalModelConfiguration = Override<CamelizeKeys<OpenApiConfig>, {
  registeredModels: string[];
  primaryModel: string;
  agentModel: string;
  importedModels?: ImportedLocalModelMetadata[];
}>;

export interface LocalModelProgress {
  modelId: string;
  percent: number | null;
  status: string;
}

export type LocalModelRuntimeState = Override<CamelizeKeys<OpenApiRuntime>, {
  status: LocalModelRuntimeStatus;
  installedModels: string[];
  localInstallPlatform: 'macos' | 'windows' | null;
  configuration: LocalModelConfiguration;
  managed?: boolean;
  operation?: string | null;
  totalMemoryGb?: number | null;
  progress?: LocalModelProgress | null;
}>;

export type LocalModelPullAccepted = Override<CamelizeKeys<OpenApiPullAccepted>, {
  status: TaskLifecycleStatus;
}>;

export type LocalModelPullResult = CamelizeKeys<OpenApiPullResult>;

export type LocalModelPullStatus = Override<CamelizeKeys<OpenApiPullStatus>, {
  status: TaskLifecycleStatus;
  result?: LocalModelPullResult | null;
}>;

export type LocalModelMutationResponse = Override<CamelizeKeys<OpenApiMutation>, {
  registeredModels: string[];
  primaryModel: string;
  agentModel: string;
  importedModels?: ImportedLocalModelMetadata[];
  updatedKeys: string[];
  warnings: string[];
}>;

export type LocalModelUnregistrationResponse = Override<CamelizeKeys<OpenApiUnregister>, {
  registeredModels: string[];
  primaryModel: string;
  agentModel: string;
  importedModels?: ImportedLocalModelMetadata[];
  updatedKeys: string[];
  warnings: string[];
  recoveryToken: string;
}>;

export type ModelPackImportAccepted = Override<CamelizeKeys<OpenApiPackAccepted>, {
  status: 'accepted';
}>;

export type ModelPackImportResult = Override<CamelizeKeys<OpenApiPackResult>, {
  warnings: string[];
}>;

export type ModelPackImportStatus = Override<CamelizeKeys<OpenApiPackStatus>, {
  status: TaskLifecycleStatus;
  result?: ModelPackImportResult | null;
}>;
