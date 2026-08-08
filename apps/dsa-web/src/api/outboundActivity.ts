// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type {
  LocalOnlyModeStatus,
  OutboundActivityListQuery,
  OutboundActivityPage,
} from '../types/outboundActivity';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

const localOnlyModeStatusSchema = z.object({
  enabled: z.boolean(),
  envKey: z.string(),
  policy: z.string(),
  allowedDestinationClasses: z.array(z.string()),
  blockedErrorReason: z.string(),
}).passthrough();

const outboundActivityItemSchema = z.object({
  occurredAt: z.string(),
  decision: z.enum(['allowed', 'blocked']),
  destinationClass: z.string(),
  scheme: z.string(),
  hostType: z.string(),
  reason: z.string(),
  correlationId: z.string(),
  localOnlyMode: z.boolean(),
  allowlisted: z.boolean(),
}).passthrough();

const outboundActivityPageSchema = z.object({
  localOnlyMode: z.boolean(),
  items: z.array(outboundActivityItemSchema),
  limit: z.number(),
  returned: z.number(),
  maxRetained: z.number(),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues.slice(0, 5).map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`).join('; ');
    throw createApiError(createParsedApiError({
      title: '响应校验失败',
      message: `接口响应未通过校验（${label}）。${issueSummary}`,
      rawMessage: result.error.message,
      category: 'unknown',
      code: 'api_response_validation_failed',
      params: { label, issues: issueSummary },
      details: result.error.issues,
    }));
  }
  return camel as T;
}

export const outboundActivityApi = {
  async getLocalOnlyStatus(): Promise<LocalOnlyModeStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/security/local-only',
      locallyRecoverableResourceConfig(),
    );
    return parseCamelCasePayload<LocalOnlyModeStatus>(response.data, localOnlyModeStatusSchema, 'LocalOnlyModeStatus');
  },
  async listActivity(query: OutboundActivityListQuery = {}): Promise<OutboundActivityPage> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/security/outbound-activity',
      { ...locallyRecoverableResourceConfig(), params: { ...(query.limit === undefined ? {} : { limit: query.limit }) } },
    );
    return parseCamelCasePayload<OutboundActivityPage>(response.data, outboundActivityPageSchema, 'OutboundActivityPage');
  },
};
