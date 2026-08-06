import { z } from 'zod';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

export type AuthStatusResponse = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet?: boolean;
  passwordChangeable?: boolean;
  setupState: 'enabled' | 'password_retained' | 'no_password';
};

const authStatusSchema = z.object({
  authEnabled: z.boolean(),
  loggedIn: z.boolean(),
  passwordSet: z.boolean().optional(),
  passwordChangeable: z.boolean().optional(),
  setupState: z.string(),
}).passthrough();

function parseAuthStatusPayload(data: unknown, label: string): AuthStatusResponse {
  const camel = toCamelCase<unknown>(data);
  const result = authStatusSchema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues.slice(0, 5).map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`).join('; ');
    if (import.meta.env.DEV) {
      console.error(`[auth] response validation failed (${label})`, result.error.issues);
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
  return camel as AuthStatusResponse;
}

/** Auth client: login/session cookie behavior unchanged; only status-shaped bodies are validated. */
export const authApi = {
  async getStatus(): Promise<AuthStatusResponse> {
    const { data } = await apiClient.get<Record<string, unknown>>('/api/v1/auth/status');
    return parseAuthStatusPayload(data, 'AuthStatus');
  },

  async updateSettings(
    authEnabled: boolean,
    password?: string,
    passwordConfirm?: string,
    currentPassword?: string,
  ): Promise<AuthStatusResponse> {
    const body: {
      authEnabled: boolean;
      password?: string;
      passwordConfirm?: string;
      currentPassword?: string;
    } = { authEnabled };
    if (password !== undefined) body.password = password;
    if (passwordConfirm !== undefined) body.passwordConfirm = passwordConfirm;
    if (currentPassword !== undefined) body.currentPassword = currentPassword;
    const { data } = await apiClient.post<Record<string, unknown>>('/api/v1/auth/settings', body);
    return parseAuthStatusPayload(data, 'AuthStatus');
  },

  async login(password: string, passwordConfirm?: string): Promise<void> {
    const body: { password: string; passwordConfirm?: string } = { password };
    if (passwordConfirm !== undefined) body.passwordConfirm = passwordConfirm;
    await apiClient.post('/api/v1/auth/login', body);
  },

  async changePassword(currentPassword: string, newPassword: string, newPasswordConfirm: string): Promise<void> {
    await apiClient.post('/api/v1/auth/change-password', {
      currentPassword,
      newPassword,
      newPasswordConfirm,
    });
  },

  async logout(): Promise<void> {
    await apiClient.post('/api/v1/auth/logout');
  },
};
