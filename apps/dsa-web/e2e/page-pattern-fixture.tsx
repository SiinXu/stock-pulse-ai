// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  createBrowserRouter,
  Outlet,
  RouterProvider,
  useNavigate,
} from 'react-router-dom';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import {
  Button,
  PageHeader,
  ResponsiveRail,
  SummaryStrip,
  TabPanel,
  Tabs,
  Toolbar,
  WorkspaceNavigation,
  WorkspacePage,
  type WorkspaceNavItem,
} from '../src/components/common';
import { RouteFocusCoordinator, useRouteFocusTarget } from '../src/components/routing';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

const WORKSPACE_ITEMS: readonly WorkspaceNavItem[] = [
  { id: 'overview', label: 'Overview', to: '/e2e/page-pattern-fixture.html' },
  { id: 'details', label: 'Detailed evidence', to: '/e2e/page-pattern-fixture.html/details' },
];

const TAB_ITEMS = [
  { id: 'summary', label: 'Summary' },
  { id: 'unavailable', label: 'Unavailable', disabled: true },
  { id: 'risk', label: 'Risk and freshness' },
] as const;

function PatternPage({ routeId, title }: { routeId: string; title: string }) {
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [tab, setTab] = useState('summary');
  useRouteFocusTarget({ routeId, headingRef, ready: true });

  useEffect(() => {
    document.title = `${title} | StockPulse`;
  }, [title]);

  const rail = (
    <ResponsiveRail
      title="Workspace context"
      expandLabel="Show workspace context"
      collapseLabel="Hide workspace context"
    >
      <div className="space-y-3 text-sm text-secondary-text">
        <p data-testid="rail-content">This context stays secondary to the active analysis task.</p>
        <p>Updated after the latest completed run.</p>
      </div>
    </ResponsiveRail>
  );

  return (
    <WorkspacePage rail={rail} contentClassName="space-y-5">
      <PageHeader
        ref={headingRef}
        eyebrow="Research workspace"
        title={title}
        description="Review the decision, supporting evidence, risk, and freshness without losing route context."
        actions={routeId === 'details' ? (
          <Button
            variant="secondary"
            size="default"
            data-route-focus-key="page-pattern:back"
            onClick={() => void navigate(-1)}
          >
            Back
          </Button>
        ) : undefined}
      />

      <WorkspaceNavigation
        id="fixture-workspace-navigation"
        ariaLabel="Workspace views"
        current={routeId}
        items={WORKSPACE_ITEMS}
        onCompactNavigate={(item) => void navigate(item.to)}
      />

      <Toolbar
        aria-label="Workspace commands"
        left={(
          <>
            <Button variant="outline" size="compact">Refresh</Button>
            <Button
              variant="outline"
              size="compact"
              onClick={() => void navigate({ search: '?view=compact' })}
            >
              Update URL state
            </Button>
          </>
        )}
        right={<Button variant="secondary" size="compact">Export</Button>}
      />

      <SummaryStrip
        aria-label="Analysis summary"
        items={[
          { id: 'decision', label: 'Decision', value: routeId === 'details' ? 'Review' : 'Hold' },
          { id: 'confidence', label: 'Confidence', value: '72%' },
          { id: 'freshness', label: 'Freshness', value: 'Today', detail: '15:30 local' },
          { id: 'risk', label: 'Risk status', value: 'Watch', tone: 'warning' },
        ]}
      />

      <section aria-labelledby={`${routeId}-analysis-heading`}>
        <h2 id={`${routeId}-analysis-heading`} className="text-base font-semibold tracking-normal text-foreground">
          Analysis sections
        </h2>
        <Tabs
          id={`${routeId}-analysis-tabs`}
          aria-label="Analysis sections"
          value={tab}
          items={TAB_ITEMS}
          onValueChange={setTab}
          className="mt-3"
        />
        <TabPanel tabsId={`${routeId}-analysis-tabs`} value="summary" activeValue={tab}>
          <p className="text-sm text-secondary-text">The current decision remains visible as the primary task outcome.</p>
        </TabPanel>
        <TabPanel tabsId={`${routeId}-analysis-tabs`} value="unavailable" activeValue={tab}>
          <p className="text-sm text-secondary-text">This section is unavailable.</p>
        </TabPanel>
        <TabPanel tabsId={`${routeId}-analysis-tabs`} value="risk" activeValue={tab}>
          <p className="text-sm text-secondary-text">Risk is elevated when evidence becomes stale.</p>
        </TabPanel>
      </section>
    </WorkspacePage>
  );
}

function FixtureShell() {
  return (
    <main className="min-h-dvh bg-background text-foreground">
      <RouteFocusCoordinator>
        <Outlet />
      </RouteFocusCoordinator>
    </main>
  );
}

const router = createBrowserRouter([
  {
    path: '/e2e/page-pattern-fixture.html',
    element: <FixtureShell />,
    children: [
      { index: true, element: <PatternPage routeId="overview" title="Portfolio overview" /> },
      {
        path: 'details',
        element: (
          <PatternPage
            routeId="details"
            title="Detailed evidence and risk review for the current portfolio"
          />
        ),
      },
    ],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider initialLanguage="en">
        <RouterProvider router={router} />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
