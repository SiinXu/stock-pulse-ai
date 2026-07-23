import type React from 'react';
import { lazy, useEffect, useState } from 'react';
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
  useLocation,
} from 'react-router-dom';
import { ApiErrorAlert, ToastProvider } from './components/common';
import { Shell } from './components/layout/Shell';
import {
  PageLoadingFallback,
  RouteOutletBoundary,
  StandaloneRouteBoundary,
} from './components/layout/RouteBoundary';
import { DeepLinkGuard } from './components/routing/DeepLinkGuard';
import { SessionContinuityGuard } from './components/routing/SessionContinuityGuard';
import { RouteFocusCoordinator } from './components/routing';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { UiLanguageProvider, useUiLanguage } from './contexts/UiLanguageContext';
import type { UiLanguage } from './i18n/uiLanguages';
import { LegacyRouteRedirect } from './routing/LegacyRedirectRoute';
import {
  APP_ROUTE_PATHS,
  LEGACY_ROUTE_PATHS,
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
} from './routing/routes';
import { useAgentChatStore } from './stores/agentChatStore';
import { resolveLoginRedirect } from './utils/loginRedirect';
import './App.css';

const HomePage = lazy(() => import('./pages/HomePage'));
const MarketReviewPage = lazy(() => import('./pages/MarketReviewPage'));
const BacktestPage = lazy(() => import('./pages/BacktestPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'));
const DecisionSignalsPage = lazy(() => import('./pages/DecisionSignalsPage'));
const AlertsPage = lazy(() => import('./pages/AlertsPage'));
const StockScreeningPage = lazy(() => import('./pages/StockScreeningPage'));
const StockDetailsPage = lazy(() => import('./pages/StockDetailsPage'));
const ComponentPlaygroundPage = lazy(() => import('./playground/ComponentPlaygroundPage'));
const PlaygroundRenderPage = lazy(() => import('./playground/PlaygroundRenderPage'));

const AppLayout: React.FC = () => {
  const location = useLocation();
  const {
    authEnabled,
    loggedIn,
    isLoading,
    loadError,
    logoutRedirectPending,
    refreshStatus,
  } = useAuth();
  const { t } = useUiLanguage();

  useEffect(() => {
    useAgentChatStore.getState().setCurrentRoute(location.pathname);
  }, [location.pathname]);

  if (isLoading) {
    return <PageLoadingFallback />;
  }

  if (loadError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-base px-4">
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

  const isLoginRoute = location.pathname === APP_ROUTE_PATHS.login;

  if (authEnabled && !loggedIn) {
    if (isLoginRoute) {
      return <Outlet />;
    }
    if (logoutRedirectPending) {
      return <Navigate to={APP_ROUTE_PATHS.login} replace />;
    }
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${APP_ROUTE_PATHS.login}?redirect=${redirect}`} replace />;
  }

  if (isLoginRoute) {
    // Preserve the deep link: every path into /login carries ?redirect=,
    // and the post-login re-render must not race LoginPage back to "/".
    return <Navigate to={resolveLoginRedirect(location.search)} replace />;
  }

  return (
    <SessionContinuityGuard>
      <Outlet />
    </SessionContinuityGuard>
  );
};

// Data router (instead of declarative <BrowserRouter>) so pages can use
// useBlocker to guard in-app navigation (e.g. unsaved settings drafts).
const routes = [
  {
    element: (
      <AuthProvider>
        <RouteFocusCoordinator>
          <DeepLinkGuard>
            <AppLayout />
          </DeepLinkGuard>
        </RouteFocusCoordinator>
      </AuthProvider>
    ),
    children: [
      {
        path: APP_ROUTE_PATHS.login,
        element: (
          <StandaloneRouteBoundary>
            <LoginPage />
          </StandaloneRouteBoundary>
        ),
      },
      {
        path: APP_ROUTE_PATHS.playground,
        element: (
          <StandaloneRouteBoundary>
            <ComponentPlaygroundPage />
          </StandaloneRouteBoundary>
        ),
      },
      {
        path: APP_ROUTE_PATHS.playgroundRender,
        element: (
          <StandaloneRouteBoundary>
            <PlaygroundRenderPage />
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
          { path: APP_ROUTE_PATHS.home, element: <HomePage /> },
          { path: APP_ROUTE_PATHS.agent, element: <ChatPage /> },
          { path: APP_ROUTE_PATHS.portfolio, element: <PortfolioPage /> },
          { path: APP_ROUTE_PATHS.decisionSignals, element: <DecisionSignalsPage /> },
          { path: APP_ROUTE_PATHS.stockDetails, element: <StockDetailsPage /> },
          { path: APP_ROUTE_PATHS.researchMarket, element: <MarketReviewPage /> },
          { path: APP_ROUTE_PATHS.researchDiscover, element: <StockScreeningPage /> },
          { path: APP_ROUTE_PATHS.researchBacktest, element: <BacktestPage /> },
          { path: APP_ROUTE_PATHS.alerts, element: <AlertsPage /> },
          {
            path: LEGACY_ROUTE_PATHS.screening,
            element: <LegacyRouteRedirect to={APP_ROUTE_PATHS.researchDiscover} />,
          },
          {
            path: LEGACY_ROUTE_PATHS.backtest,
            element: <LegacyRouteRedirect to={APP_ROUTE_PATHS.researchBacktest} />,
          },
          {
            path: LEGACY_ROUTE_PATHS.usage,
            element: (
              <LegacyRouteRedirect
                to={APP_ROUTE_PATHS.settings}
                overrideSearchParams={{
                  [SETTINGS_ROUTE_QUERY_KEYS.section]: SETTINGS_SECTION_IDS.usage,
                }}
              />
            ),
          },
          { path: APP_ROUTE_PATHS.settings, element: <SettingsPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

const App: React.FC<{ initialUiLanguage?: UiLanguage }> = ({ initialUiLanguage }) => {
  // Created on mount (not at module scope) so each mount picks up the current
  // window.location — tests push a URL right before rendering <App />.
  const [router] = useState(() => createBrowserRouter(routes));

  return (
    <UiLanguageProvider initialLanguage={initialUiLanguage}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </UiLanguageProvider>
  );
};

export default App;
