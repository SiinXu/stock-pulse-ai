// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import apiClient from './index';
import { getParsedApiError } from './error';
import { toCamelCase } from './utils';
import type {
  InvestmentFrameworkCreateRequest,
  InvestmentFrameworkDeactivateRequest,
  InvestmentFrameworkDeleteResponse,
  InvestmentFrameworkHistoryResponse,
  InvestmentFrameworkResponse,
  InvestmentFrameworkUpdateRequest,
} from '../types/investmentFramework';

const BASE_PATH = '/api/v1/investment-framework';

function snakeKey(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function toSnakeUnknown(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(toSnakeUnknown);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .map(([key, nested]) => [snakeKey(key), toSnakeUnknown(nested)]),
    );
  }
  return value;
}

function unknownFields(
  value: Record<string, unknown>,
  knownKeys: readonly string[],
): Record<string, unknown> {
  const known = new Set(knownKeys);
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !known.has(key))
      .map(([key, nested]) => [snakeKey(key), toSnakeUnknown(nested)]),
  );
}

function toSnakeContent(content: InvestmentFrameworkCreateRequest['content']): Record<string, unknown> {
  return {
    ...unknownFields(content, [
      'schemaVersion',
      'title',
      'description',
      'rootNodeId',
      'decisionTree',
      'evaluationDimensions',
      'riskRules',
      'trackingCriteria',
      'freeFormRules',
    ]),
    schema_version: content.schemaVersion ?? 'investment-framework-content-v1',
    title: content.title,
    description: content.description ?? null,
    root_node_id: content.rootNodeId ?? null,
    decision_tree: (content.decisionTree ?? []).map((node) => ({
      ...unknownFields(node, ['nodeId', 'question', 'branches']),
      node_id: node.nodeId,
      question: node.question,
      branches: node.branches.map((branch) => ({
        ...unknownFields(branch, ['condition', 'targetNodeId', 'outcome']),
        condition: branch.condition,
        target_node_id: branch.targetNodeId ?? null,
        outcome: branch.outcome ?? null,
      })),
    })),
    evaluation_dimensions: (content.evaluationDimensions ?? []).map((item) => ({
      ...unknownFields(item, ['name', 'weight', 'criteria', 'description']),
      name: item.name,
      weight: item.weight,
      criteria: item.criteria ?? [],
      description: item.description ?? null,
    })),
    risk_rules: content.riskRules ?? [],
    tracking_criteria: content.trackingCriteria ?? [],
    free_form_rules: content.freeFormRules ?? null,
  };
}

export const investmentFrameworkApi = {
  async get(): Promise<InvestmentFrameworkResponse> {
    try {
      const response = await apiClient.get(BASE_PATH);
      return toCamelCase<InvestmentFrameworkResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async create(payload: InvestmentFrameworkCreateRequest): Promise<InvestmentFrameworkResponse> {
    try {
      const response = await apiClient.post(BASE_PATH, {
        content: toSnakeContent(payload.content),
        change_summary: payload.changeSummary ?? null,
      });
      return toCamelCase<InvestmentFrameworkResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async update(payload: InvestmentFrameworkUpdateRequest): Promise<InvestmentFrameworkResponse> {
    try {
      const response = await apiClient.put(BASE_PATH, {
        expected_revision: payload.expectedRevision,
        content: toSnakeContent(payload.content),
        change_summary: payload.changeSummary ?? null,
      });
      return toCamelCase<InvestmentFrameworkResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async deactivate(
    payload: InvestmentFrameworkDeactivateRequest,
  ): Promise<InvestmentFrameworkResponse> {
    try {
      const response = await apiClient.post(`${BASE_PATH}/deactivate`, {
        expected_revision: payload.expectedRevision,
      });
      return toCamelCase<InvestmentFrameworkResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async remove(expectedRevision: number): Promise<InvestmentFrameworkDeleteResponse> {
    try {
      const response = await apiClient.delete(BASE_PATH, {
        params: { expected_revision: expectedRevision },
      });
      return toCamelCase<InvestmentFrameworkDeleteResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async history(): Promise<InvestmentFrameworkHistoryResponse> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/history`);
      return toCamelCase<InvestmentFrameworkHistoryResponse>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },
};
