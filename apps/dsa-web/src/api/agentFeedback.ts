// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';

type OpenApiAgentRunFeedbackItem = components['schemas']['AgentRunFeedbackItem'];
type OpenApiAgentRunFeedbackRequest = components['schemas']['AgentRunFeedbackRequest'];
type _AssertItemFields = keyof OpenApiAgentRunFeedbackItem;
type _AssertRequestFields = keyof OpenApiAgentRunFeedbackRequest;
const _itemFieldAnchor: _AssertItemFields = 'run_id';
const _requestFieldAnchor: _AssertRequestFields = 'feedback_value';
void _itemFieldAnchor;
void _requestFieldAnchor;

export const AGENT_RUN_FEEDBACK_VALUES = ['useful', 'partial', 'wrong', 'harmful'] as const;
export type AgentRunFeedbackValue = (typeof AGENT_RUN_FEEDBACK_VALUES)[number];

export const AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH = 1000;
export const AGENT_RUN_ID_MAX_LENGTH = 128;

export type AgentRunFeedbackItem = {
  runId: string;
  feedbackValue: AgentRunFeedbackValue | null;
  note: string | null;
  source: 'web' | 'api' | null;
  provenanceSource: 'system_resolve' | 'user_feedback' | 'operator' | null;
  actorId: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type AgentRunFeedbackRequest = {
  feedbackValue: AgentRunFeedbackValue;
  note: string;
  source: 'web';
};

const agentRunFeedbackValueSchema = z.enum(AGENT_RUN_FEEDBACK_VALUES);

const agentRunFeedbackItemSchema = z.object({
  runId: z.string(),
  feedbackValue: agentRunFeedbackValueSchema.nullable().optional(),
  note: z.string().nullable().optional(),
  source: z.enum(['web', 'api']).nullable().optional(),
  provenanceSource: z.enum(['system_resolve', 'user_feedback', 'operator']).nullable().optional(),
  actorId: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

/**
 * Canonical run identity for GET/PUT `/agent/runs/{run_id}/feedback`.
 * Empty, whitespace, internal whitespace, or tokens longer than 128 are rejected
 * so the client never issues a path that would 422.
 */
export function canonicalizeAgentRunId(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > AGENT_RUN_ID_MAX_LENGTH || /\s/.test(trimmed)) {
    return null;
  }
  return trimmed;
}

function agentRunFeedbackPath(runId: string): string {
  return `/api/v1/agent/runs/${encodeURIComponent(runId)}/feedback`;
}

function toSnakeRunFeedbackPayload(payload: AgentRunFeedbackRequest): Record<string, unknown> {
  return {
    feedback_value: payload.feedbackValue,
    note: payload.note,
    source: payload.source,
  };
}

function toAgentRunFeedbackItem(data: unknown): AgentRunFeedbackItem {
  const item = parseCamelCasePayload<AgentRunFeedbackItem>(
    data,
    agentRunFeedbackItemSchema,
    'AgentRunFeedbackItem',
    'agentFeedback',
  );
  return {
    ...item,
    feedbackValue: item.feedbackValue ?? null,
    note: item.note ?? null,
    source: item.source ?? null,
    provenanceSource: item.provenanceSource ?? null,
    actorId: item.actorId ?? null,
    createdAt: item.createdAt ?? null,
    updatedAt: item.updatedAt ?? null,
  };
}

export const agentFeedbackApi = {
  async getRunFeedback(runId: string): Promise<AgentRunFeedbackItem> {
    const response = await apiClient.get<Record<string, unknown>>(agentRunFeedbackPath(runId));
    return toAgentRunFeedbackItem(response.data);
  },

  async putRunFeedback(
    runId: string,
    payload: AgentRunFeedbackRequest,
  ): Promise<AgentRunFeedbackItem> {
    const response = await apiClient.put<Record<string, unknown>>(
      agentRunFeedbackPath(runId),
      toSnakeRunFeedbackPayload(payload),
    );
    return toAgentRunFeedbackItem(response.data);
  },
};
