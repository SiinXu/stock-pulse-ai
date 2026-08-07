import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authApi } from '../auth';
import { getParsedApiError, isApiRequestError } from '../error';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
}));

describe('authApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('parses camelCase status payloads without changing field names', async () => {
    get.mockResolvedValueOnce({
      data: {
        authEnabled: true,
        loggedIn: false,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      },
    });
    const status = await authApi.getStatus();
    expect(get).toHaveBeenCalledWith('/api/v1/auth/status');
    expect(status).toEqual({
      authEnabled: true,
      loggedIn: false,
      passwordSet: true,
      passwordChangeable: true,
      setupState: 'enabled',
    });
  });

  it('preserves extra keys on valid status payloads (pass-through)', async () => {
    get.mockResolvedValueOnce({
      data: {
        authEnabled: false,
        loggedIn: false,
        setupState: 'no_password',
        unexpectedServerField: 'keep-me',
      },
    });
    const status = await authApi.getStatus();
    expect(status).toEqual({
      authEnabled: false,
      loggedIn: false,
      setupState: 'no_password',
      unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces status shape mismatches through ParsedApiError', async () => {
    get.mockResolvedValueOnce({
      data: { authEnabled: true, setupState: 'enabled' },
    });
    await expect(authApi.getStatus()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('AuthStatus');
      return true;
    });
  });

  it('posts login/settings/change-password/logout bodies without consuming success bodies', async () => {
    post.mockResolvedValue({ data: { ok: true }, status: 200 });

    await authApi.login('secret', 'secret');
    expect(post).toHaveBeenCalledWith('/api/v1/auth/login', {
      password: 'secret',
      passwordConfirm: 'secret',
    });

    await authApi.changePassword('old', 'new', 'new');
    expect(post).toHaveBeenCalledWith('/api/v1/auth/change-password', {
      currentPassword: 'old',
      newPassword: 'new',
      newPasswordConfirm: 'new',
    });

    await authApi.logout();
    expect(post).toHaveBeenCalledWith('/api/v1/auth/logout');

    post.mockResolvedValueOnce({
      data: {
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      },
    });
    const settings = await authApi.updateSettings(true, 'pw', 'pw');
    expect(post).toHaveBeenCalledWith('/api/v1/auth/settings', {
      authEnabled: true,
      password: 'pw',
      passwordConfirm: 'pw',
    });
    expect(settings.loggedIn).toBe(true);
  });

  it('propagates transport errors so the 401 interceptor path remains intact', async () => {
    const unauthorized = Object.assign(new Error('Unauthorized'), {
      response: { status: 401, data: { detail: { error: 'unauthorized' } } },
      config: { url: '/api/v1/auth/login' },
    });
    post.mockRejectedValueOnce(unauthorized);
    await expect(authApi.login('bad')).rejects.toBe(unauthorized);

    get.mockRejectedValueOnce(unauthorized);
    await expect(authApi.getStatus()).rejects.toBe(unauthorized);
  });
});
