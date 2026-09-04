import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import type {
  UsageDashboard,
  UsagePeriod,
} from '../types/usage';

export type {
  UsagePeriod,
  UsageCallTypeBreakdown,
  UsageModelBreakdown,
  UsageStageBreakdown,
  UsageAgentModeBreakdown,
  UsageCallRecord,
  UsageDashboard,
} from '../types/usage';

type OpenApiUsageDashboard = components['schemas']['UsageDashboardResponse'];
type OpenApiUsageCallRecord = components['schemas']['UsageCallRecord'];
type _AssertDashboard = keyof OpenApiUsageDashboard;
type _AssertCallRecord = keyof OpenApiUsageCallRecord;
const _dashboardAnchor: _AssertDashboard = 'period';
const _callRecordAnchor: _AssertCallRecord = 'called_at';
void _dashboardAnchor;
void _callRecordAnchor;

const usageCallTypeBreakdownSchema = z.object({
  callType: z.string(),
  calls: z.number(),
  promptTokens: z.number().optional(),
  completionTokens: z.number().optional(),
  totalTokens: z.number(),
}).passthrough();

const usageModelBreakdownSchema = z.object({
  model: z.string(),
  calls: z.number(),
  promptTokens: z.number().optional(),
  completionTokens: z.number().optional(),
  totalTokens: z.number(),
  maxTotalTokens: z.number().optional(),
}).passthrough();

const usageCallRecordSchema = z.object({
  id: z.number(),
  calledAt: z.string(),
  callType: z.string(),
  model: z.string(),
  stockCode: z.string().nullable().optional(),
  promptTokens: z.number(),
  completionTokens: z.number(),
  totalTokens: z.number(),
}).passthrough();

const usageDashboardSchema = z.object({
  period: z.string(),
  fromDate: z.string(),
  toDate: z.string(),
  totalCalls: z.number(),
  totalPromptTokens: z.number().optional(),
  totalCompletionTokens: z.number().optional(),
  totalTokens: z.number(),
  byCallType: z.array(usageCallTypeBreakdownSchema),
  byModel: z.array(usageModelBreakdownSchema),
  recentCalls: z.array(usageCallRecordSchema),
}).passthrough();

export const usageApi = {
  getDashboard: async (params: { period?: UsagePeriod; limit?: number } = {}): Promise<UsageDashboard> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/usage/dashboard', {
      params: { period: params.period ?? 'month', limit: params.limit ?? 50 },
    });
    return parseCamelCasePayload<UsageDashboard>(
      response.data,
      usageDashboardSchema,
      'UsageDashboardResponse',
      'usage',
    );
  },
};
