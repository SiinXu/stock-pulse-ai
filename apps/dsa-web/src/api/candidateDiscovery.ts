// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import apiClient from './index';
import type { components } from '../types/api.generated';

type OpenApiCandidateDiscoveryResponse = components['schemas']['CandidateDiscoveryResponse'];
type OpenApiCandidateDiscoveryCandidate = components['schemas']['CandidateDiscoveryCandidate'];
type OpenApiCandidateDiscoveryTaskAccepted = components['schemas']['CandidateDiscoveryTaskAccepted'];
type OpenApiCandidateDiscoveryTaskStatus = components['schemas']['CandidateDiscoveryTaskStatus'];

// Compile-time anchor: hand-written camelCase types stay aligned with OpenAPI
// field sets (rename detection is structural; extra optional UI fields are fine).
type _AssertDiscoveryResponse = keyof OpenApiCandidateDiscoveryResponse;
type _AssertDiscoveryCandidate = keyof OpenApiCandidateDiscoveryCandidate;
type _AssertDiscoveryAccepted = keyof OpenApiCandidateDiscoveryTaskAccepted;
type _AssertDiscoveryStatus = keyof OpenApiCandidateDiscoveryTaskStatus;
const _discoveryResponseAnchor: _AssertDiscoveryResponse = 'pack_version';
const _discoveryCandidateAnchor: _AssertDiscoveryCandidate = 'change_pct';
const _discoveryAcceptedAnchor: _AssertDiscoveryAccepted = 'task_id';
const _discoveryStatusAnchor: _AssertDiscoveryStatus = 'task_id';
void _discoveryResponseAnchor;
void _discoveryCandidateAnchor;
void _discoveryAcceptedAnchor;
void _discoveryStatusAnchor;

const candidateSchema = z.object({
  rank: z.number(),
  code: z.string(),
  name: z.string().optional(),
  score: z.number().nullable().optional(),
  reason: z.string().optional(),
  reasonCodes: z.array(z.string()).optional(),
  riskLevel: z.string().optional(),
  price: z.number().nullable().optional(),
  changePct: z.number().nullable().optional(),
  amount: z.number().nullable().optional(),
  industry: z.string().nullable().optional(),
  factorScores: z.record(z.string(), z.number()).optional(),
  llmThesis: z.string().nullable().optional(),
  market: z.string().nullable().optional(),
  provider: z.string().nullable().optional(),
  selectionSource: z.string().nullable().optional(),
}).passthrough();

const discoveryResponseSchema = z.object({
  packVersion: z.string(),
  runId: z.string(),
  status: z.string(),
  query: z.string().optional(),
  universe: z.string(),
  market: z.string().optional(),
  page: z.number().optional(),
  pageSize: z.number().optional(),
  maxResults: z.number().optional(),
  candidateCount: z.number(),
  candidates: z.array(z.record(z.string(), z.unknown())).optional(),
  criteria: z.record(z.string(), z.unknown()).optional(),
  emptyReason: z.string().nullable().optional(),
  emptyMessage: z.string().nullable().optional(),
  warnings: z.array(z.string()).optional(),
  researchDisclaimer: z.string().optional(),
  universeContract: z.record(z.string(), z.unknown()).optional(),
  costContract: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const taskAcceptedSchema = z.object({
  taskId: z.string(),
  traceId: z.string(),
  status: z.string(),
  message: z.string(),
  messageCode: z.string().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  universe: z.string(),
  page: z.number(),
  pageSize: z.number(),
  maxResults: z.number(),
  maxProviderCalls: z.number(),
}).passthrough();

const taskStatusSchema = z.object({
  taskId: z.string(),
  traceId: z.string().nullable().optional(),
  status: z.string(),
  progress: z.number().optional(),
  message: z.string().nullable().optional(),
  messageCode: z.string().nullable().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  error: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
}).passthrough();

export type DiscoveryUniverse = 'watchlist' | 'portfolio' | 'index' | 'codes';

export type CandidateDiscoveryRequest = {
  query?: string;
  universe?: DiscoveryUniverse | string;
  page?: number;
  pageSize?: number;
  maxResults?: number;
  maxProviderCalls?: number;
  codes?: string[];
  markets?: string[];
  useLlm?: boolean;
  language?: 'en' | 'zh';
};

export type DiscoveryCandidate = {
  rank: number;
  code: string;
  name: string;
  score?: number | null;
  reason: string;
  reasonCodes?: string[];
  riskLevel?: string;
  price?: number | null;
  changePct?: number | null;
  amount?: number | null;
  industry?: string;
  factorScores?: Record<string, number>;
  llmThesis?: string;
  market?: string;
  provider?: string;
  selectionSource?: string;
  raw: Record<string, unknown>;
};

export type CandidateDiscoveryResponse = {
  packVersion: string;
  runId: string;
  status: string;
  query?: string;
  universe: string;
  market?: string;
  page?: number;
  pageSize?: number;
  maxResults?: number;
  candidateCount: number;
  candidates: DiscoveryCandidate[];
  criteria?: Record<string, unknown>;
  emptyReason?: string | null;
  emptyMessage?: string | null;
  warnings?: string[];
  researchDisclaimer?: string;
  universeContract?: Record<string, unknown>;
  costContract?: Record<string, unknown>;
};

export type CandidateDiscoveryTaskAccepted = {
  taskId: string;
  traceId: string;
  status: string;
  message: string;
  universe: string;
  page: number;
  pageSize: number;
  maxResults: number;
  maxProviderCalls: number;
};

export type CandidateDiscoveryTaskStatus = {
  taskId: string;
  traceId?: string | null;
  status: string;
  progress?: number;
  message?: string | null;
  error?: string | null;
  result?: CandidateDiscoveryResponse | null;
};

function mapCandidate(raw: Record<string, unknown>): DiscoveryCandidate {
  const parsed = parseCamelCasePayload<z.infer<typeof candidateSchema>>(
    raw,
    candidateSchema,
    'candidate discovery candidate',
    'candidateDiscovery',
  );
  return {
    rank: parsed.rank,
    code: parsed.code,
    name: parsed.name || parsed.code,
    score: parsed.score ?? null,
    reason: parsed.reason || '',
    reasonCodes: parsed.reasonCodes,
    riskLevel: parsed.riskLevel,
    price: parsed.price ?? null,
    changePct: parsed.changePct ?? null,
    amount: parsed.amount ?? null,
    industry: parsed.industry || undefined,
    factorScores: parsed.factorScores,
    llmThesis: parsed.llmThesis || undefined,
    market: parsed.market || undefined,
    provider: parsed.provider || undefined,
    selectionSource: parsed.selectionSource || undefined,
    raw,
  };
}

function mapResponse(payload: unknown): CandidateDiscoveryResponse {
  const parsed = parseCamelCasePayload<z.infer<typeof discoveryResponseSchema>>(
    payload,
    discoveryResponseSchema,
    'candidate discovery response',
    'candidateDiscovery',
  );
  const candidates = (parsed.candidates || []).map((item) => {
    return mapCandidate(item);
  });
  return {
    ...parsed,
    candidates,
  };
}

export const candidateDiscoveryApi = {
  startTask: async (body: CandidateDiscoveryRequest): Promise<CandidateDiscoveryTaskAccepted> => {
    const { data } = await apiClient.post('/api/v1/discover/screen/tasks', body);
    const parsed = parseCamelCasePayload<z.infer<typeof taskAcceptedSchema>>(
      data,
      taskAcceptedSchema,
      'candidate discovery task accepted',
      'candidateDiscovery',
    );
    return parsed;
  },

  getTask: async (taskId: string): Promise<CandidateDiscoveryTaskStatus> => {
    const { data } = await apiClient.get(`/api/v1/discover/screen/tasks/${encodeURIComponent(taskId)}`);
    const parsed = parseCamelCasePayload<z.infer<typeof taskStatusSchema>>(
      data,
      taskStatusSchema,
      'candidate discovery task status',
      'candidateDiscovery',
    );
    return {
      ...parsed,
      result: parsed.result ? mapResponse(parsed.result) : null,
    };
  },

  cancelTask: async (taskId: string): Promise<CandidateDiscoveryTaskStatus> => {
    const { data } = await apiClient.post(`/api/v1/discover/screen/tasks/${encodeURIComponent(taskId)}/cancel`);
    const parsed = parseCamelCasePayload<z.infer<typeof taskStatusSchema>>(
      data,
      taskStatusSchema,
      'candidate discovery cancel status',
      'candidateDiscovery',
    );
    return {
      ...parsed,
      result: parsed.result ? mapResponse(parsed.result) : null,
    };
  },
};
