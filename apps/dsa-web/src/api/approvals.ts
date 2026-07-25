import type {
  ApprovalDecision,
  ApprovalProposal,
  ApprovalProposalPage,
  ApprovalRule,
  ApprovalRuleUpdate,
  ApprovalStatus,
} from '../types/approvals';
import apiClient from './index';
import { toCamelCase } from './utils';

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
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/approvals/rules/risk-control-bypass',
    );
    return toCamelCase<ApprovalRule>(response.data);
  },

  async updateRule(rule: ApprovalRuleUpdate): Promise<ApprovalRule> {
    const response = await apiClient.put<Record<string, unknown>>(
      '/api/v1/approvals/rules/risk-control-bypass',
      toSnakeRule(rule),
    );
    return toCamelCase<ApprovalRule>(response.data);
  },

  async list(params: {
    page?: number;
    pageSize?: number;
    status?: ApprovalStatus;
  } = {}): Promise<ApprovalProposalPage> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/approvals',
      {
        params: {
          page: params.page,
          page_size: params.pageSize,
          status: params.status,
        },
      },
    );
    return toCamelCase<ApprovalProposalPage>(response.data);
  },

  async get(proposalId: string): Promise<ApprovalProposal> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/approvals/${encodeURIComponent(proposalId)}`,
    );
    return toCamelCase<ApprovalProposal>(response.data);
  },

  async decide(
    proposalId: string,
    decision: ApprovalDecision,
    expectedVersion: number,
  ): Promise<ApprovalProposal> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/approvals/${encodeURIComponent(proposalId)}/decision`,
      {
        decision,
        expected_version: expectedVersion,
      },
    );
    return toCamelCase<ApprovalProposal>(response.data);
  },
};
