import { z } from 'zod';
import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import {
  createApiError,
  createParsedApiError,
  isApiRequestError,
  parseApiError,
} from './error';
// Generated OpenAPI components document the backend snake_case contract for
// plain (non-streaming) agent request/response surfaces.
import type { components } from '../types/api.generated';

type OpenApiChatResponse = components['schemas']['ChatResponse'];
type OpenApiResearchResponse = components['schemas']['ResearchResponse'];
type OpenApiSkillsResponse = components['schemas']['SkillsResponse'];
type OpenApiSessionsResponse = components['schemas']['SessionsResponse'];
type OpenApiSessionMessagesResponse = components['schemas']['SessionMessagesResponse'];

type _AssertChatFields = keyof OpenApiChatResponse;
type _AssertResearchFields = keyof OpenApiResearchResponse;
type _AssertSkillsFields = keyof OpenApiSkillsResponse;
type _AssertSessionsFields = keyof OpenApiSessionsResponse;
type _AssertMessagesFields = keyof OpenApiSessionMessagesResponse;
const _chatFieldAnchor: _AssertChatFields = 'session_id';
const _researchFieldAnchor: _AssertResearchFields = 'token_usage';
const _skillsFieldAnchor: _AssertSkillsFields = 'default_skill_id';
const _sessionsFieldAnchor: _AssertSessionsFields = 'sessions';
const _messagesFieldAnchor: _AssertMessagesFields = 'messages';
void _chatFieldAnchor;
void _researchFieldAnchor;
void _skillsFieldAnchor;
void _sessionsFieldAnchor;
void _messagesFieldAnchor;

export interface ChatStreamOptions {
  signal?: AbortSignal;
}

export interface ChatRequest {
  message: string;
  skills?: string[];
}

export interface ChatStreamRequest extends ChatRequest {
  session_id?: string;
  context?: unknown;
}

/** Snake_case response shapes match OpenAPI and existing Chat UI consumers. */
export interface ChatResponse {
  success: boolean;
  content: string;
  session_id: string;
  error?: string | null;
  agent_runtime?: {
    soul_version: string;
    soul_hash: string;
  } | null;
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
}

export interface SkillsResponse {
  skills: SkillInfo[];
  default_skill_id: string;
}

export interface ChatSessionItem {
  session_id: string;
  title: string;
  message_count: number;
  created_at: string | null;
  last_active: string | null;
}

export interface ChatSessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string | null;
  error?: string | null;
  params?: Record<string, unknown> | null;
}

export interface ResearchRequest {
  question: string;
  stockCode?: string;
}

export interface ResearchResponse {
  success: boolean;
  content: string;
  sources: string[];
  token_usage: number;
  error?: string | null;
}

/**
 * Agent plain JSON responses stay snake_case (no toCamelCase) so valid payloads
 * remain byte-identical to the pre-validation path used by Chat UI.
 */
const agentRuntimeSchema = z.object({
  soul_version: z.string(),
  soul_hash: z.string(),
}).passthrough();

const chatResponseSchema = z.object({
  success: z.boolean(),
  content: z.string(),
  session_id: z.string(),
  error: z.string().nullable().optional(),
  agent_runtime: agentRuntimeSchema.nullable().optional(),
}).passthrough();

const researchResponseSchema = z.object({
  success: z.boolean(),
  content: z.string(),
  sources: z.array(z.string()).optional(),
  token_usage: z.number(),
  error: z.string().nullable().optional(),
}).passthrough();

const skillInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
}).passthrough();

const skillsResponseSchema = z.object({
  skills: z.array(skillInfoSchema),
  default_skill_id: z.string(),
}).passthrough();

const sessionItemSchema = z.object({
  session_id: z.string(),
  title: z.string(),
  message_count: z.number(),
  created_at: z.string().nullable().optional(),
  last_active: z.string().nullable().optional(),
}).passthrough();

const sessionsResponseSchema = z.object({
  sessions: z.array(sessionItemSchema),
}).passthrough();

const sessionMessageSchema = z.object({
  id: z.string(),
  role: z.string(),
  content: z.string(),
  created_at: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  params: z.record(z.string(), z.unknown()).nullable().optional(),
}).passthrough();

const sessionMessagesResponseSchema = z.object({
  session_id: z.string(),
  messages: z.array(sessionMessageSchema),
}).passthrough();

function parseSnakeCasePayload<T>(
  data: unknown,
  schema: z.ZodTypeAny,
  label: string,
): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[agent] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  // Return the original object so valid payloads stay byte-identical.
  return data as T;
}

export const agentApi = {
  // Deep Research is synchronous (no task id / SSE); it can take up to ~180s,
  // so allow a long timeout and support cancellation via an AbortSignal.
  async research(
    payload: ResearchRequest,
    options?: { signal?: AbortSignal },
  ): Promise<ResearchResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/agent/research',
      { question: payload.question, stock_code: payload.stockCode },
      { timeout: 200000, signal: options?.signal },
    );
    const parsed = parseSnakeCasePayload<ResearchResponse>(
      response.data,
      researchResponseSchema,
      'ResearchResponse',
    );
    // OpenAPI marks sources optional; consumers always expect an array.
    if (!Array.isArray(parsed.sources)) {
      return { ...parsed, sources: [] };
    }
    return parsed;
  },
  async chat(payload: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/agent/chat', payload, {
      timeout: 120000,
    });
    return parseSnakeCasePayload<ChatResponse>(
      response.data,
      chatResponseSchema,
      'ChatResponse',
    );
  },
  async getSkills(): Promise<SkillsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/agent/skills');
    return parseSnakeCasePayload<SkillsResponse>(
      response.data,
      skillsResponseSchema,
      'SkillsResponse',
    );
  },
  async getChatSessions(limit = 50): Promise<ChatSessionItem[]> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/agent/chat/sessions',
      { params: { limit } },
    );
    const data = parseSnakeCasePayload<{ sessions: ChatSessionItem[] }>(
      response.data,
      sessionsResponseSchema,
      'SessionsResponse',
    );
    return data.sessions;
  },
  async getChatSessionMessages(sessionId: string): Promise<ChatSessionMessage[]> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/agent/chat/sessions/${encodeURIComponent(sessionId)}`,
    );
    const data = parseSnakeCasePayload<{ messages: ChatSessionMessage[] }>(
      response.data,
      sessionMessagesResponseSchema,
      'SessionMessagesResponse',
    );
    return data.messages;
  },
  async deleteChatSession(sessionId: string): Promise<void> {
    // OpenAPI response body is unknown; no structured validation.
    await apiClient.delete(`/api/v1/agent/chat/sessions/${encodeURIComponent(sessionId)}`);
  },
  async sendChat(content: string): Promise<{ success: boolean }> {
    // OpenAPI response content is unknown; keep the prior success gate.
    const response = await apiClient.post<{
      success: boolean;
      error?: string;
      message?: string;
    }>('/api/v1/agent/chat/send', { content });
    const data = response.data;
    if (data.success === false) {
      throw new Error(data.message || '发送失败');
    }
    return { success: true };
  },
  /**
   * Documented skip for issue #721: SSE/streaming surface stays unvalidated.
   * Follow-up: migrate stream error envelopes if a stable JSON error shape is
   * added to the OpenAPI document for failed stream starts.
   */
  async chatStream(
    payload: ChatStreamRequest,
    options?: ChatStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/agent/chat/stream`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
        signal: options?.signal,
      });

      if (response.ok) {
        return response;
      }

      const contentType = response.headers.get('content-type') || '';
      let responseData: unknown = null;
      if (contentType.includes('application/json')) {
        responseData = await response.json().catch(() => null);
      } else {
        responseData = await response.text().catch(() => null);
      }

      const parsed = parseApiError({
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
      throw createApiError(parsed, {
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
    } catch (error: unknown) {
      if (isApiRequestError(error)) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }

      const parsed = parseApiError(error);
      throw createApiError(parsed, { cause: error });
    }
  },
};
