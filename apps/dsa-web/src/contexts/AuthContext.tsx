import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { authApi } from '../api/auth';
import { useAgentChatStore } from '../stores/agentChatStore';
import { useStockPoolStore } from '../stores/stockPoolStore';
import { clearPersistedWebSession } from '../utils/sessionPersistence';

type AuthContextValue = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet: boolean;
  passwordChangeable: boolean;
  setupState: 'enabled' | 'password_retained' | 'no_password';
  isLoading: boolean;
  loadError: ParsedApiError | null;
  logoutRedirectPending: boolean;
  login: (password: string, passwordConfirm?: string) => Promise<{ success: boolean; error?: ParsedApiError }>;
  changePassword: (
    currentPassword: string,
    newPassword: string,
    newPasswordConfirm: string
  ) => Promise<{ success: boolean; error?: ParsedApiError }>;
  logout: () => Promise<void>;
  refreshStatus: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function extractLoginError(err: unknown): ParsedApiError {
  return getParsedApiError(err);
}

function resetPrivateClientSession(): void {
  clearPersistedWebSession();
  useAgentChatStore.getState().resetSessionState();
  useStockPoolStore.getState().resetDashboardState();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [passwordSet, setPasswordSet] = useState(false);
  const [passwordChangeable, setPasswordChangeable] = useState(false);
  const [setupState, setSetupState] = useState<'enabled' | 'password_retained' | 'no_password'>('no_password');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [logoutRedirectPending, setLogoutRedirectPending] = useState(false);

  // Guard against out-of-order status responses: a stale in-flight request
  // (e.g. the initial mount fetch) must not overwrite the state written by a
  // newer one (e.g. the post-login refresh), or the route guard bounces a
  // freshly logged-in user back to /login.
  const statusRequestSeq = useRef(0);

  const fetchStatus = useCallback(async () => {
    const requestId = ++statusRequestSeq.current;
    setIsLoading(true);
    setLoadError(null);
    try {
      const status = await authApi.getStatus();
      if (requestId !== statusRequestSeq.current) {
        return;
      }
      setAuthEnabled(status.authEnabled);
      setLoggedIn(status.loggedIn);
      setPasswordSet(status.passwordSet ?? false);
      setPasswordChangeable(status.passwordChangeable ?? false);
      setSetupState(status.setupState);
      if (status.authEnabled && !status.loggedIn) {
        resetPrivateClientSession();
      }
    } catch (err) {
      if (requestId !== statusRequestSeq.current) {
        return;
      }
      setLoadError(getParsedApiError(err));
      setAuthEnabled(false);
      setLoggedIn(false);
      setPasswordSet(false);
      setPasswordChangeable(false);
      setSetupState('no_password');
      // A transient status failure does not prove that the authenticated session ended.
      // Preserve tab-scoped continuity so a successful retry can resume the workflow.
      useStockPoolStore.getState().resetDashboardState();
    } finally {
      if (requestId === statusRequestSeq.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const login = useCallback(
    async (
      password: string,
      passwordConfirm?: string
    ): Promise<{ success: boolean; error?: ParsedApiError }> => {
      setLogoutRedirectPending(false);
      try {
        await authApi.login(password, passwordConfirm);
        await fetchStatus();
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: extractLoginError(err) };
      }
    },
    [fetchStatus]
  );

  const changePassword = useCallback(
    async (
      currentPassword: string,
      newPassword: string,
      newPasswordConfirm: string
    ): Promise<{ success: boolean; error?: ParsedApiError }> => {
      try {
        await authApi.changePassword(currentPassword, newPassword, newPasswordConfirm);
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: getParsedApiError(err) };
      }
    },
    []
  );

  const logout = useCallback(async () => {
    setLogoutRedirectPending(true);
    let logoutError: unknown = null;
    try {
      await authApi.logout();
      resetPrivateClientSession();
    } catch (err) {
      logoutError = err;
      if (getParsedApiError(err).status === 401) {
        resetPrivateClientSession();
      }
    } finally {
      await fetchStatus();
    }

    if (logoutError && getParsedApiError(logoutError).status !== 401) {
      setLogoutRedirectPending(false);
      throw logoutError;
    }
  }, [fetchStatus]);

  return (
    <AuthContext.Provider
      value={{
        authEnabled,
        loggedIn,
        passwordSet,
        passwordChangeable,
        setupState,
        isLoading,
        loadError,
        logoutRedirectPending,
        login,
        changePassword,
        logout,
        refreshStatus: fetchStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- useAuth is a hook, co-located for context access
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
