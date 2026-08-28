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

const LEGAL_SETUP_STATES = ['enabled', 'password_retained', 'no_password'] as const;

function validStatus(overrides: Record<string, unknown> = {}) {
  return {
    authEnabled: true,
    loggedIn: false,
    passwordSet: true,
    passwordChangeable: true,
    setupState: 'enabled',
    ...overrides,
  };
}

function expectValidationFailed(error: unknown): boolean {
  expect(isApiRequestError(error)).toBe(true);
  const parsed = getParsedApiError(error);
  expect(parsed.code).toBe('api_response_validation_failed');
  expect(parsed.message).toContain('AuthStatus');
  return true;
}

describe('authApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('parses camelCase status payloads without changing field names', async () => {
    get.mockResolvedValueOnce({
      data: validStatus(),
    });
    const status = await authApi.getStatus();
    expect(get).toHaveBeenCalledWith('/api/v1/auth/status');
    expect(status).toEqual(validStatus());
  });

  it.each(LEGAL_SETUP_STATES)('accepts legal setupState %s on GET status', async (setupState) => {
    get.mockResolvedValueOnce({
      data: validStatus({
        authEnabled: setupState === 'enabled',
        passwordSet: setupState !== 'no_password',
        passwordChangeable: setupState !== 'no_password',
        setupState,
      }),
    });
    const status = await authApi.getStatus();
    expect(status.setupState).toBe(setupState);
  });

  it('rejects an illegal setupState enum value', async () => {
    get.mockResolvedValueOnce({
      data: validStatus({ setupState: 'disabled' }),
    });
    await expect(authApi.getStatus()).rejects.toSatisfy(expectValidationFailed);
  });

  it('rejects a status payload missing passwordSet', async () => {
    const { passwordSet: _omitted, ...withoutPasswordSet } = validStatus();
    void _omitted;
    get.mockResolvedValueOnce({ data: withoutPasswordSet });
    await expect(authApi.getStatus()).rejects.toSatisfy((error: unknown) => {
      expectValidationFailed(error);
      expect(getParsedApiError(error).message).toMatch(/passwordSet/i);
      return true;
    });
  });

  it('rejects a status payload missing passwordChangeable', async () => {
    const { passwordChangeable: _omitted, ...withoutPasswordChangeable } = validStatus();
    void _omitted;
    get.mockResolvedValueOnce({ data: withoutPasswordChangeable });
    await expect(authApi.getStatus()).rejects.toSatisfy((error: unknown) => {
      expectValidationFailed(error);
      expect(getParsedApiError(error).message).toMatch(/passwordChangeable/i);
      return true;
    });
  });

  it('preserves extra keys on valid status payloads (pass-through)', async () => {
    get.mockResolvedValueOnce({
      data: validStatus({
        authEnabled: false,
        loggedIn: false,
        passwordSet: false,
        passwordChangeable: false,
        setupState: 'no_password',
        unexpectedServerField: 'keep-me',
      }),
    });
    const status = await authApi.getStatus();
    expect(status).toEqual({
      authEnabled: false,
      loggedIn: false,
      passwordSet: false,
      passwordChangeable: false,
      setupState: 'no_password',
      unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces malformed GET status responses through ParsedApiError', async () => {
    get.mockResolvedValueOnce({
      data: { authEnabled: true, setupState: 'enabled' },
    });
    await expect(authApi.getStatus()).rejects.toSatisfy(expectValidationFailed);
  });

  it('surfaces malformed POST settings responses through the same parser', async () => {
    post.mockResolvedValueOnce({
      data: { authEnabled: true, loggedIn: true, setupState: 'enabled' },
    });
    await expect(authApi.updateSettings(true, 'pw', 'pw')).rejects.toSatisfy(expectValidationFailed);
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
      data: validStatus({ loggedIn: true }),
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

    post.mockRejectedValueOnce(unauthorized);
    await expect(authApi.updateSettings(false)).rejects.toBe(unauthorized);
  });
});
