// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- Vite-only fixture defines and mounts its harness in one entry file */
import { StrictMode, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  createBrowserRouter,
  Outlet,
  RouterProvider,
  useLocation,
} from 'react-router-dom';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { PageHeader } from '../src/components/common';
import { Shell } from '../src/components/layout/Shell';
import { RouteFocusCoordinator, useRouteFocusTarget } from '../src/components/routing';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { AuthProvider } from '../src/contexts/AuthContext';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

function FixturePage() {
  const location = useLocation();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const routeId = location.pathname;
  useRouteFocusTarget({ routeId, headingRef, ready: true });

  useEffect(() => {
    document.title = `Shell ${routeId} | StockPulse`;
  }, [routeId]);

  return (
    <section className="min-h-full w-full p-4 sm:p-6 lg:p-8" data-testid="shell-fixture-content">
      <PageHeader
        ref={headingRef}
        eyebrow="Application shell"
        title={`Route ${routeId}`}
        description="Deterministic content verifies navigation without adopting a business page."
      />
      <div className="mt-6 grid min-w-0 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {['Market context', 'Decision evidence', 'Risk summary'].map((label) => (
          <section key={label} className="min-w-0 border-t border-border pt-3">
            <h2 className="text-sm font-semibold text-foreground">{label}</h2>
            <p className="mt-1 break-words text-sm text-secondary-text">
              Shell content remains readable without an outer framed card or horizontal clipping.
            </p>
          </section>
        ))}
      </div>
    </section>
  );
}

const router = createBrowserRouter([
  {
    element: (
      <RouteFocusCoordinator>
        <Shell>
          <Outlet />
        </Shell>
      </RouteFocusCoordinator>
    ),
    children: [{ path: '*', element: <FixturePage /> }],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider initialLanguage="en">
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
