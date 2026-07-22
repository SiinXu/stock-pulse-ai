/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { Route, Routes } from 'react-router-dom';
import { Button } from '../../components/common';
import { DashboardPanelHeader, DashboardStateBlock } from '../../components/dashboard';
import { UiLanguageToggle } from '../../components/i18n/UiLanguageToggle';
import {
  PageLoadingFallback,
  RouteBoundary,
  RouteOutletBoundary,
  StandaloneRouteBoundary,
} from '../../components/layout/RouteBoundary';
import { Shell } from '../../components/layout/Shell';
import { SidebarNav } from '../../components/layout/SidebarNav';
import { SidebarProfile } from '../../components/layout/SidebarProfile';
import { RouteFocusCoordinator } from '../../components/routing';
import { DeepLinkGuard } from '../../components/routing/DeepLinkGuard';
import { SessionContinuityGuard } from '../../components/routing/SessionContinuityGuard';
import { ThemeToggle } from '../../components/theme/ThemeToggle';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const useSamples = () => {
  const { language } = useUiLanguage();
  return PLAYGROUND_TEXT[language].samples;
};

const ShellStory = () => {
  const text = useSamples();
  return (
    <Shell>
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="w-full max-w-xl rounded-lg border border-border bg-background p-6 text-center text-sm text-secondary-text">
          {text.preview}
        </div>
      </div>
    </Shell>
  );
};

const SidebarNavStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [collapsed, setCollapsed] = useState(scenario === 'states');
  return (
    <aside className={collapsed ? 'flex h-[calc(100dvh-3rem)] w-15 flex-col' : 'flex h-[calc(100dvh-3rem)] w-56 flex-col'}>
      <SidebarNav collapsed={collapsed} onToggleCollapse={() => setCollapsed((value) => !value)} />
    </aside>
  );
};

const SidebarProfileStory = () => (
  <aside className="flex h-64 w-56 flex-col justify-end">
    <SidebarProfile />
  </aside>
);

const ThemeToggleStory = () => (
  <div className="flex min-h-48 items-start justify-center rounded-lg border border-border bg-card p-6">
    <ThemeToggle />
  </div>
);

const UiLanguageToggleStory = () => (
  <div className="flex min-h-48 items-start justify-center rounded-lg border border-border bg-card p-6">
    <UiLanguageToggle />
  </div>
);

const ThrowingRouteContent = ({ message }: { message: string }) => {
  throw new Error(message);
};

const RoutePreviewContent = () => {
  const text = useSamples();
  return <div className="rounded-lg border border-border bg-card p-6 text-sm text-secondary-text">{text.preview}</div>;
};

const RouteBoundaryStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  return (
    <RouteBoundary fullPage={false}>
      {scenario === 'error' ? <ThrowingRouteContent message={text.error} /> : <RoutePreviewContent />}
    </RouteBoundary>
  );
};

const RouteOutletBoundaryStory = () => (
  <Routes>
    <Route element={<RouteOutletBoundary />}>
      <Route path="*" element={<RoutePreviewContent />} />
    </Route>
  </Routes>
);

const StandaloneRouteBoundaryStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  return (
    <StandaloneRouteBoundary>
      {scenario === 'error' ? <ThrowingRouteContent message={text.error} /> : <RoutePreviewContent />}
    </StandaloneRouteBoundary>
  );
};

const RouteFocusCoordinatorStory = () => (
  <RouteFocusCoordinator>
    <RoutePreviewContent />
  </RouteFocusCoordinator>
);

const DeepLinkGuardStory = () => (
  <DeepLinkGuard>
    <RoutePreviewContent />
  </DeepLinkGuard>
);

const SessionContinuityGuardStory = () => (
  <SessionContinuityGuard>
    <RoutePreviewContent />
  </SessionContinuityGuard>
);

const DashboardPanelHeaderStory = () => {
  const text = useSamples();
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <DashboardPanelHeader
        eyebrow={text.panelEyebrow}
        title={text.panelTitle}
        leading={<Activity className="h-4 w-4 text-primary" aria-hidden="true" />}
        accentEyebrow
        actions={<Button variant="secondary" size="compact">{text.secondaryAction}</Button>}
      />
      <p className="text-sm text-secondary-text">{text.preview}</p>
    </div>
  );
};

const DashboardStateBlockStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  return (
    <div className="rounded-lg border border-border bg-card">
      <DashboardStateBlock
        loading={scenario === 'loading'}
        title={scenario === 'loading' ? text.loadingAction : text.emptyTitle}
        description={scenario === 'loading' ? text.loadingDescription : text.emptyDescription}
        icon={scenario === 'loading' ? undefined : <Activity className="h-5 w-5" aria-hidden="true" />}
        action={scenario === 'empty' ? <Button variant="secondary"><RefreshCw />{text.retry}</Button> : undefined}
      />
    </div>
  );
};

export const LAYOUT_DASHBOARD_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  shell: ShellStory,
  'sidebar-nav': SidebarNavStory,
  'sidebar-profile': SidebarProfileStory,
  'page-loading-fallback': PageLoadingFallback,
  'route-boundary': RouteBoundaryStory,
  'route-outlet-boundary': RouteOutletBoundaryStory,
  'standalone-route-boundary': StandaloneRouteBoundaryStory,
  'deep-link-guard': DeepLinkGuardStory,
  'session-continuity-guard': SessionContinuityGuardStory,
  'route-focus-coordinator': RouteFocusCoordinatorStory,
  'theme-toggle': ThemeToggleStory,
  'ui-language-toggle': UiLanguageToggleStory,
  'dashboard-panel-header': DashboardPanelHeaderStory,
  'dashboard-state-block': DashboardStateBlockStory,
};
