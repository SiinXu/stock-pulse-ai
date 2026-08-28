import { z } from 'zod';
import apiClient from './index';
import type { components } from '../types/api.generated';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiAuthSettingsRequest = components['schemas']['AuthSettingsRequest'];
type OpenApiAuthStatusResponse = components['schemas']['AuthStatusResponse'];

export type AuthStatusResponse = OpenApiAuthStatusResponse;

type _AssertAuthSettings = keyof OpenApiAuthSettingsRequest;
const _authSettingsAnchor: _AssertAuthSettings = 'authEnabled';
void _authSettingsAnchor;

type _AssertAuthStatus = keyof OpenApiAuthStatusResponse;
const _authStatusAnchor: _AssertAuthStatus = 'passwordChangeable';
void _authStatusAnchor;

const AUTH_SETUP_STATES = ['enabled', 'password_retained', 'no_password'] as const;
type AuthSetupState = AuthStatusResponse['setupState'];
type _AssertSetupStateExhaustive = Exclude<AuthSetupState, (typeof AUTH_SETUP_STATES)[number]> extends never
  ? Exclude<(typeof AUTH_SETUP_STATES)[number], AuthSetupState> extends never
    ? true
    : never
  : never;
const _setupStateExhaustive: _AssertSetupStateExhaustive = true;
void _setupStateExhaustive;

const authStatusSchema = z.object({
  authEnabled: z.boolean(),
  loggedIn: z.boolean(),
  passwordSet: z.boolean(),
  passwordChangeable: z.boolean(),
  setupState: z.enum(AUTH_SETUP_STATES),
}).passthrough();

function parseAuthStatusPayload(data: unknown, label: string): AuthStatusResponse {
  return parseCamelCasePayload<AuthStatusResponse>(data, authStatusSchema, label, 'auth');
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
