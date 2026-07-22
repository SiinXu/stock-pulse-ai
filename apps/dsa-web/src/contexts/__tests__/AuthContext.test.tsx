import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../api/error';
import { AuthProvider, useAuth } from '../AuthContext';

const {
  getStatus,
  login,
  changePassword,
  logout,
  resetChatSessionState,
  resetDashboardState,
  clearPersistedWebSession,
} = vi.hoisted(() => ({
  getStatus: vi.fn(),
  login: vi.fn(),
  changePassword: vi.fn(),
  logout: vi.fn(),
  resetChatSessionState: vi.fn(),
  resetDashboardState: vi.fn(),
  clearPersistedWebSession: vi.fn(),
}));

vi.mock('../../api/auth', () => ({
  authApi: {
    getStatus,
    login,
    changePassword,
    logout,
  },
}));

vi.mock('../../stores/stockPoolStore', () => ({
  useStockPoolStore: {
    getState: () => ({
      resetDashboardState,
    }),
  },
}));

vi.mock('../../stores/agentChatStore', () => ({
  useAgentChatStore: {
    getState: () => ({
      resetSessionState: resetChatSessionState,
    }),
  },
}));

vi.mock('../../utils/sessionPersistence', () => ({
  clearPersistedWebSession,
}));

const Probe = () => {
  const auth = useAuth();

  return (
    <div>
      <span data-testid="status">{auth.loggedIn ? 'logged-in' : 'logged-out'}</span>
      <span data-testid="password-set">{auth.passwordSet ? 'set' : 'unset'}</span>
      <span data-testid="logout-redirect">{auth.logoutRedirectPending ? 'pending' : 'idle'}</span>
      <button type="button" onClick={() => void auth.login('passwd6', 'passwd6')}>
        trigger-login
      </button>
      <button type="button" onClick={() => void auth.logout().catch(() => undefined)}>
        trigger-logout
      </button>
    </div>
  );
};

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('refreshes auth state after a successful login', async () => {
    getStatus
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: false,
        passwordSet: false,
        passwordChangeable: true,
      })
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
      });
    login.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    fireEvent.click(screen.getByRole('button', { name: 'trigger-login' }));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('logged-in'));
    expect(screen.getByTestId('password-set')).toHaveTextContent('set');
  });

  it('ignores a stale status response that resolves after a newer one', async () => {
    let resolveInitialStatus: (value: unknown) => void = () => {};
    const initialStatus = new Promise((resolve) => {
      resolveInitialStatus = resolve;
    });
    getStatus.mockReturnValueOnce(initialStatus).mockResolvedValueOnce({
      authEnabled: true,
      loggedIn: true,
      passwordSet: true,
      passwordChangeable: true,
      setupState: 'enabled',
    });
    login.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    fireEvent.click(screen.getByRole('button', { name: 'trigger-login' }));
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('logged-in'));

    await act(async () => {
      resolveInitialStatus({
        authEnabled: true,
        loggedIn: false,
        passwordSet: false,
        passwordChangeable: true,
        setupState: 'no_password',
      });
      await initialStatus;
    });

    expect(screen.getByTestId('status')).toHaveTextContent('logged-in');
    expect(screen.getByTestId('password-set')).toHaveTextContent('set');
    expect(resetDashboardState).not.toHaveBeenCalled();
  });

  it('refreshes auth state after logout', async () => {
    getStatus
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
      })
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: false,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      });
    logout.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    fireEvent.click(screen.getByRole('button', { name: 'trigger-logout' }));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('logged-out'));
    expect(screen.getByTestId('logout-redirect')).toHaveTextContent('pending');
    expect(resetDashboardState).toHaveBeenCalled();
    expect(resetChatSessionState).toHaveBeenCalled();
    expect(clearPersistedWebSession).toHaveBeenCalled();
  });

  it('clears explicit logout redirect intent when logout is not confirmed', async () => {
    let rejectLogout: (reason?: unknown) => void = () => {};
    const pendingLogout = new Promise((_, reject) => {
      rejectLogout = reject;
    });
    getStatus
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      })
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      });
    logout.mockReturnValueOnce(pendingLogout);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    fireEvent.click(screen.getByRole('button', { name: 'trigger-logout' }));
    await waitFor(() => expect(screen.getByTestId('logout-redirect')).toHaveTextContent('pending'));

    await act(async () => {
      rejectLogout(new Error('logout unavailable'));
      await pendingLogout.catch(() => undefined);
    });

    await waitFor(() => expect(screen.getByTestId('logout-redirect')).toHaveTextContent('idle'));
    expect(screen.getByTestId('status')).toHaveTextContent('logged-in');
    expect(clearPersistedWebSession).not.toHaveBeenCalled();
  });

  it('does not reset dashboard state when auth is disabled', async () => {
    getStatus.mockResolvedValueOnce({
      authEnabled: false,
      loggedIn: false,
      passwordSet: false,
      passwordChangeable: false,
      setupState: 'no_password',
    });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    expect(resetDashboardState).not.toHaveBeenCalled();
    expect(resetChatSessionState).not.toHaveBeenCalled();
    expect(clearPersistedWebSession).not.toHaveBeenCalled();
  });

  it('preserves persisted session continuity when auth status is temporarily unavailable', async () => {
    getStatus.mockRejectedValueOnce(new Error('network unavailable'));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    await waitFor(() => expect(resetDashboardState).toHaveBeenCalled());
    expect(resetChatSessionState).not.toHaveBeenCalled();
    expect(clearPersistedWebSession).not.toHaveBeenCalled();
  });

  it('treats a 401 logout as already signed out after status refresh', async () => {
    getStatus
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: true,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      })
      .mockResolvedValueOnce({
        authEnabled: true,
        loggedIn: false,
        passwordSet: true,
        passwordChangeable: true,
        setupState: 'enabled',
      });
    logout.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '未登录',
          message: 'Login required',
          rawMessage: 'Login required',
          status: 401,
          category: 'http_error',
        }),
        { response: { status: 401, data: { error: 'unauthorized' } } }
      )
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByTestId('status');
    fireEvent.click(screen.getByRole('button', { name: 'trigger-logout' }));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('logged-out'));
    expect(screen.getByTestId('logout-redirect')).toHaveTextContent('pending');
    expect(resetDashboardState).toHaveBeenCalled();
    expect(resetChatSessionState).toHaveBeenCalled();
    expect(clearPersistedWebSession).toHaveBeenCalled();
  });
});
