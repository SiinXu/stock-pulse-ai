// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';

type OpenApiCapabilityResponse = components['schemas']['CapabilityListResponse'];
type OpenApiCapabilitySource = components['schemas']['CapabilitySourceStatus'];
type OpenApiCapabilityItem =
  | components['schemas']['DataCapabilityItem']
  | components['schemas']['ToolCapabilityItem']
  | components['schemas']['ExtensionCapabilityItem']
  | components['schemas']['SkillCapabilityItem']
  | components['schemas']['PipelineCapabilityItem'];

const _responseFieldAnchor: keyof OpenApiCapabilityResponse = 'schema_version';
const _sourceFieldAnchor: keyof OpenApiCapabilitySource = 'generation';
const _itemFieldAnchor: keyof OpenApiCapabilityItem = 'source_generation';
void _responseFieldAnchor;
void _sourceFieldAnchor;
void _itemFieldAnchor;

const capabilityDomainSchema = z.enum(['data', 'tool', 'extension', 'skill', 'pipeline']);
const sourceStateSchema = z.enum(['ok', 'error', 'generation_drift', 'not_initialized']);

const capabilitySourceSchema = z.object({
  source: capabilityDomainSchema,
  state: sourceStateSchema,
  generation: z.string().min(1),
  as_of: z.string().min(1),
  error_code: z.string().nullable().optional(),
}).passthrough();

const capabilityItemBaseSchema = z.object({
  id: z.string().min(1),
  owner: z.string().min(1),
  provider: z.string().min(1),
  version: z.string().min(1),
  source_generation: z.string().min(1),
  as_of: z.string().min(1),
  registered: z.boolean(),
  configured: z.boolean().nullable().optional(),
  dependency_ready: z.boolean().nullable().optional(),
  grantable: z.boolean().nullable().optional(),
  executable: z.boolean().nullable().optional(),
  healthy: z.boolean().nullable().optional(),
  degraded: z.boolean().nullable().optional(),
  dependencies: z.array(z.string()).optional(),
  scopes: z.array(z.string()).optional(),
  markets: z.array(z.string()).optional(),
  providers: z.array(z.string()).optional(),
  provider_count: z.number().int().nonnegative().nullable().optional(),
  reason_code: z.string().nullable().optional(),
  display_name: z.string(),
});

const capabilityItemSchema = z.discriminatedUnion('domain', [
  capabilityItemBaseSchema.extend({
    domain: z.literal('data'),
    type: z.enum(['data_provider', 'data_method']),
  }),
  capabilityItemBaseSchema.extend({ domain: z.literal('tool'), type: z.literal('agent_tool') }),
  capabilityItemBaseSchema.extend({
    domain: z.literal('extension'),
    type: z.enum(['plugin_lifecycle', 'extension_registration']),
  }),
  capabilityItemBaseSchema.extend({ domain: z.literal('skill'), type: z.literal('analysis_skill') }),
  capabilityItemBaseSchema.extend({ domain: z.literal('pipeline'), type: z.literal('pipeline_stage') }),
]);

const capabilityListResponseSchema = z.object({
  schema_version: z.literal('capability-inventory/v1'),
  partial: z.boolean(),
  sources: z.array(capabilitySourceSchema).optional(),
  items: z.array(capabilityItemSchema).optional(),
  total: z.number().int().nonnegative(),
  executable_count: z.number().int().nonnegative(),
  non_executable_count: z.number().int().nonnegative(),
  unknown_executable_count: z.number().int().nonnegative(),
}).passthrough();

function parseCapabilities(data: unknown): OpenApiCapabilityResponse {
  const result = capabilityListResponseSchema.safeParse(data);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    throw createApiError(createParsedApiError({
      title: 'Capability response validation failed',
      message: `Capability inventory did not match its API contract. ${issueSummary}`,
      rawMessage: result.error.message,
      category: 'unknown',
      code: 'api_response_validation_failed',
      params: { label: 'CapabilityListResponse', issues: issueSummary },
      details: result.error.issues,
    }));
  }
  return data as OpenApiCapabilityResponse;
}

export type CapabilityListResponse = OpenApiCapabilityResponse;
export type CapabilitySourceStatus = OpenApiCapabilitySource;
export type CapabilityItem = OpenApiCapabilityItem;

export const capabilitiesApi = {
  async list(): Promise<CapabilityListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/capabilities');
    return parseCapabilities(response.data);
  },
};
