import type React from 'react';
import { lazy, useEffect, useState } from 'react';
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
  useLocation,
} from 'react-router-dom';
import { ApiErrorAlert, Shell } from './components/common';
import {
  PageLoadingFallback,
  RouteOutletBoundary,
  StandaloneRouteBoundary,
} from './components/layout/RouteBoundary';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { UiLanguageProvider, useUiLanguage } from './contexts/UiLanguageContext';
import { useAgentChatStore } from './stores/agentChatStore';
import './App.css';

const HomePage = lazy(() => import('./pages/HomePage'));
const BacktestPage = lazy(() => import('./pages/BacktestPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'));
const DecisionSignalsPage = lazy(() => import('./pages/DecisionSignalsPage'));
const AlertsPage = lazy(() => import('./pages/AlertsPage'));
const TokenUsagePage = lazy(() => import('./pages/TokenUsagePage'));
const StockScreeningPage = lazy(() => import('./pages/StockScreeningPage'));

const AppLayout: React.FC = () => {
  const location = useLocation();
  const { authEnabled, loggedIn, isLoading, loadError, refreshStatus } = useAuth();
  const { t } = useUiLanguage();

  useEffect(() => {
    useAgentChatStore.getState().setCurrentRoute(location.pathname);
  }, [location.pathname]);

  if (isLoading) {
    return <PageLoadingFallback />;
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-base px-4">
        <div className="w-full max-w-lg">
          <ApiErrorAlert error={loadError} />
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={() => void refreshStatus()}
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  const isLoginRoute = location.pathname === '/login';

  if (authEnabled && !loggedIn) {
    if (isLoginRoute) {
      return <Outlet />;
    }
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }

  if (isLoginRoute) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
};

// Data router (instead of declarative <BrowserRouter>) so pages can use
// useBlocker to guard in-app navigation (e.g. unsaved settings drafts).
const routes = [
  {
    element: (
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    ),
    children: [
      {
        path: '/login',
        element: (
          <StandaloneRouteBoundary>
            <LoginPage />
          </StandaloneRouteBoundary>
        ),
      },
      {
        element: (
          <Shell>
            <RouteOutletBoundary />
          </Shell>
        ),
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/chat', element: <ChatPage /> },
          { path: '/portfolio', element: <PortfolioPage /> },
          { path: '/decision-signals', element: <DecisionSignalsPage /> },
          { path: '/screening', element: <StockScreeningPage /> },
          { path: '/backtest', element: <BacktestPage /> },
          { path: '/alerts', element: <AlertsPage /> },
          { path: '/usage', element: <TokenUsagePage /> },
          { path: '/settings', element: <SettingsPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

const App: React.FC = () => {
  // Created on mount (not at module scope) so each mount picks up the current
  // window.location — tests push a URL right before rendering <App />.
  const [router] = useState(() => createBrowserRouter(routes));

  return (
    <UiLanguageProvider>
      <RouterProvider router={router} />
    </UiLanguageProvider>
  );
};

export default App;
