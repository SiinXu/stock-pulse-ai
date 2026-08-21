import type React from 'react';
import { lazy, useEffect, useState } from 'react';
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
  useLocation,
} from 'react-router-dom';
import { ApiErrorAlert } from './components/common/ApiErrorAlert';
import { ToastProvider } from './components/common/ToastProvider';
import { Shell } from './components/layout/Shell';
import {
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
import { LegacyHomeAnalysisRedirect } from './routing/LegacyHomeAnalysisRedirect';
import {
  mapLegacyAlertsSearchParams,
  mapLegacyDecisionSignalsSearchParams,
} from './routing/signalCenterRouteState';
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
const ResearchOverviewPage = lazy(() => import('./pages/ResearchOverviewPage'));
const ResearchAnalysisWorkbenchPage = lazy(() => import('./pages/ResearchAnalysisWorkbenchPage'));
const MarketReviewPage = lazy(() => import('./pages/MarketReviewPage'));
const BacktestPage = lazy(() => import('./pages/BacktestPage'));
const SkillOutcomesPage = lazy(() => import('./pages/SkillOutcomesPage'));
const ReportVersionComparePage = lazy(() => import('./pages/ReportVersionComparePage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'));
const PersonalPerformancePage = lazy(() => import('./pages/PersonalPerformancePage'));
const EventCalendarPage = lazy(() => import('./pages/EventCalendarPage'));
const SignalCenterPage = lazy(() => import('./pages/DecisionSignalsPage'));
const ApprovalsPage = lazy(() => import('./pages/ApprovalsPage'));
const NotificationCenterPage = lazy(() => import('./pages/NotificationCenterPage'));
const StockScreeningPage = lazy(() => import('./pages/StockScreeningPage'));
const StockDetailsPage = lazy(() => import('./pages/StockDetailsPage'));
const EventAlertsPage = lazy(() => import('./components/event-alerts/EventAlertsPanel'));
const FinancialCalculatorsPage = lazy(() => import('./pages/FinancialCalculatorsPage'));

/** Non-textual nav frame shown before auth/status content. No copy. */
const AppShellSkeleton: React.FC = () => (
  <div
    data-app-shell-skeleton=""
    aria-busy="true"
    className="h-dvh overflow-hidden bg-background"
  >
    <div
      data-shell-mobile-header="true"
      className="pointer-events-none fixed inset-x-0 top-0 z-40 flex min-w-0 items-center gap-3 px-3 pt-[max(0.75rem,env(safe-area-inset-top))] lg:hidden"
    >
      <span className="h-10 w-10 rounded-lg bg-card shadow-soft-card" />
      <span className="h-4 max-w-[8rem] flex-1 rounded bg-muted" />
    </div>
    <div className="mx-auto flex h-full w-full overflow-hidden">
      <aside
        data-shell-sidebar="true"
        className="sticky top-0 z-40 hidden h-full w-20 shrink-0 self-start bg-background px-2 py-4 lg:flex lg:flex-col lg:items-center lg:gap-3"
      >
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
      </aside>
      <div
        data-shell-main="true"
        className="relative mt-[calc(2.75rem+max(0.75rem,env(safe-area-inset-top)))] mb-3 mx-3 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-soft-card lg:mt-4 lg:mb-4 lg:ml-1 lg:mr-4"
      />
    </div>
  </div>
);

function createPlaygroundRoutes() {
  // Keep playground pages and mocks out of the production graph. Vite replaces
  // import.meta.env.DEV at build time so the dynamic imports are tree-shaken.
  if (!import.meta.env.DEV) {
    return [];
  }
  const ComponentPlaygroundPage = lazy(() => import('./playground/ComponentPlaygroundPage'));
  const PlaygroundRenderPage = lazy(() => import('./playground/PlaygroundRenderPage'));
  return [
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
  ];
}

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
    return <AppShellSkeleton />;
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
    const redirect = encodeURIComponent(location.pathname + location.search + location.hash);
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
      ...createPlaygroundRoutes(),
      {
        element: (
          <Shell>
            <RouteOutletBoundary />
          </Shell>
        ),
        children: [
          {
            path: APP_ROUTE_PATHS.home,
            element: (
              <LegacyHomeAnalysisRedirect>
                <HomePage />
              </LegacyHomeAnalysisRedirect>
            ),
          },
          { path: APP_ROUTE_PATHS.agent, element: <ChatPage /> },
          { path: APP_ROUTE_PATHS.portfolio, element: <PortfolioPage /> },
          { path: APP_ROUTE_PATHS.portfolioPerformance, element: <PersonalPerformancePage /> },
          { path: APP_ROUTE_PATHS.eventCalendar, element: <EventCalendarPage /> },
          { path: APP_ROUTE_PATHS.signals, element: <SignalCenterPage /> },
          { path: APP_ROUTE_PATHS.approvals, element: <ApprovalsPage /> },
          { path: APP_ROUTE_PATHS.notifications, element: <NotificationCenterPage /> },
          { path: APP_ROUTE_PATHS.stockDetails, element: <StockDetailsPage /> },
          { path: APP_ROUTE_PATHS.research, element: <ResearchOverviewPage /> },
          { path: APP_ROUTE_PATHS.researchMarket, element: <MarketReviewPage /> },
          { path: APP_ROUTE_PATHS.researchDiscover, element: <StockScreeningPage /> },
          {
            path: APP_ROUTE_PATHS.researchAnalysis,
            element: <ResearchAnalysisWorkbenchPage />,
          },
          { path: APP_ROUTE_PATHS.researchBacktest, element: <BacktestPage /> },
          { path: APP_ROUTE_PATHS.researchSkillOutcomes, element: <SkillOutcomesPage /> },
          { path: APP_ROUTE_PATHS.calculators, element: <FinancialCalculatorsPage /> },
          {
            path: APP_ROUTE_PATHS.researchReportCompare,
            element: <ReportVersionComparePage />,
          },
          {
            path: LEGACY_ROUTE_PATHS.decisionSignals,
            element: (
              <LegacyRouteRedirect
                to={APP_ROUTE_PATHS.signals}
                mapSearchParams={mapLegacyDecisionSignalsSearchParams}
              />
            ),
          },
          {
            path: LEGACY_ROUTE_PATHS.alerts,
            element: (
              <LegacyRouteRedirect
                to={APP_ROUTE_PATHS.signals}
                mapSearchParams={mapLegacyAlertsSearchParams}
              />
            ),
          },
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
          { path: APP_ROUTE_PATHS.eventAlerts, element: <EventAlertsPage /> },
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
