import { z } from 'zod';
import type {
  ApprovalDecision,
  ApprovalProposal,
  ApprovalProposalPage,
  ApprovalRule,
  ApprovalRuleUpdate,
  ApprovalStatus,
} from '../types/approvals';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type { components } from '../types/api.generated';

type OpenApiApprovalRule = components['schemas']['ApprovalRule'];
type OpenApiApprovalProposal = components['schemas']['ApprovalProposal'];
type OpenApiApprovalProposalPage = components['schemas']['ApprovalProposalPage'];
type _AssertRule = keyof OpenApiApprovalRule;
type _AssertProposal = keyof OpenApiApprovalProposal;
type _AssertPage = keyof OpenApiApprovalProposalPage;
const _ruleAnchor: _AssertRule = 'risk_sources';
const _proposalAnchor: _AssertProposal = 'expires_at';
const _pageAnchor: _AssertPage = 'page_size';
void _ruleAnchor;
void _proposalAnchor;
void _pageAnchor;

const approvalContextSchema = z.object({
  stockCode: z.string().optional(),
  originalSignal: z.string(),
  conservativeSignal: z.string(),
  riskSource: z.string(),
  riskSummary: z.string(),
}).passthrough();

const approvalRuleSchema = z.object({
  owner: z.string(),
  action: z.string().optional(),
  enabled: z.boolean(),
  riskSources: z.array(z.string()),
  expiresInSeconds: z.number(),
  version: z.number(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

const approvalProposalSchema = z.object({
  id: z.string(),
  owner: z.string(),
  status: z.string(),
  version: z.number(),
  expiresAt: z.string(),
  consumedAt: z.string().nullable().optional(),
  context: approvalContextSchema,
}).passthrough();

const approvalProposalPageSchema = z.object({
  items: z.array(approvalProposalSchema),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues.slice(0, 5).map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`).join('; ');
    if (import.meta.env.DEV) {
      console.error(`[approvals] response validation failed (${label})`, result.error.issues);
    }
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

function toSnakeRule(rule: ApprovalRuleUpdate) {
  return {
    enabled: rule.enabled,
    risk_sources: rule.riskSources,
    expires_in_seconds: rule.expiresInSeconds,
    expected_version: rule.expectedVersion,
  };
}

export const approvalsApi = {
  async getRule(): Promise<ApprovalRule> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/approvals/rules/risk-control-bypass');
    return parseCamelCasePayload<ApprovalRule>(response.data, approvalRuleSchema, 'ApprovalRule');
  },
  async updateRule(rule: ApprovalRuleUpdate): Promise<ApprovalRule> {
    const response = await apiClient.put<Record<string, unknown>>('/api/v1/approvals/rules/risk-control-bypass', toSnakeRule(rule));
    return parseCamelCasePayload<ApprovalRule>(response.data, approvalRuleSchema, 'ApprovalRule');
  },
  async list(params: { page?: number; pageSize?: number; status?: ApprovalStatus } = {}): Promise<ApprovalProposalPage> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/approvals', {
      params: { page: params.page, page_size: params.pageSize, status: params.status },
    });
    return parseCamelCasePayload<ApprovalProposalPage>(response.data, approvalProposalPageSchema, 'ApprovalProposalPage');
  },
  async get(proposalId: string): Promise<ApprovalProposal> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/approvals/${encodeURIComponent(proposalId)}`);
    return parseCamelCasePayload<ApprovalProposal>(response.data, approvalProposalSchema, 'ApprovalProposal');
  },
  async decide(proposalId: string, decision: ApprovalDecision, expectedVersion: number): Promise<ApprovalProposal> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/approvals/${encodeURIComponent(proposalId)}/decision`,
      { decision, expected_version: expectedVersion },
    );
    return parseCamelCasePayload<ApprovalProposal>(response.data, approvalProposalSchema, 'ApprovalProposal');
  },
};
