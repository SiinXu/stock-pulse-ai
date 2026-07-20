// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useRef, useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  createMemoryRouter,
  Link,
  Outlet,
  RouterProvider,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { AppPage, PageHeader } from '../../common';
import { useRouteFocusTarget } from '../../../hooks/useRouteFocusTarget';
import { RouteFocusCoordinator } from '../RouteFocusCoordinator';

function RegisteredPage({
  routeId,
  title,
  ready = true,
  children,
}: {
  routeId: string;
  title: string;
  ready?: boolean;
  children?: React.ReactNode;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useRouteFocusTarget({ routeId, headingRef, ready });
  useEffect(() => {
    document.title = `${title} | StockPulse`;
  }, [title]);
  return (
    <AppPage>
      <PageHeader ref={headingRef} title={title} />
      {children}
    </AppPage>
  );
}

function FirstPage({ duplicateMarker = false }: { duplicateMarker?: boolean }) {
  return (
    <RegisteredPage routeId="first" title="First page">
      <Link
        to="/second"
        data-route-focus-key="first:second"
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey) event.preventDefault();
        }}
      >
        Open second page
      </Link>
      {duplicateMarker ? <Link to="/second" data-route-focus-key="first:second">Duplicate second link</Link> : null}
    </RegisteredPage>
  );
}

function ReplacePage() {
  const navigate = useNavigate();
  return (
    <RegisteredPage routeId="replace" title="Replace page">
      <button
        type="button"
        data-route-focus-key="replace:second"
        onClick={() => void navigate('/second', { replace: true })}
      >
        Replace with second page
      </button>
    </RegisteredPage>
  );
}

function DeferredPage() {
  const [ready, setReady] = useState(false);
  return (
    <RegisteredPage routeId="deferred" title="Deferred page" ready={ready}>
      <button type="button" onClick={() => setReady(true)}>Finish loading</button>
    </RegisteredPage>
  );
}

function SamePathUrlStatePage() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <RegisteredPage routeId="same-path" title="Same path page">
      <button
        type="button"
        data-route-focus-key="same-path:query"
        onClick={() => void navigate('/same-path?view=pushed')}
      >
        Push query state
      </button>
      <button
        type="button"
        onClick={() => void navigate('/same-path?view=replaced', { replace: true })}
      >
        Replace query state
      </button>
      <output data-testid="same-path-search">{location.search}</output>
    </RegisteredPage>
  );
}

async function flushRouteFocusFrames(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => resolve());
      });
    });
  });
}

function renderRouter(initialPath = '/first', duplicateMarker = false) {
  const router = createMemoryRouter([
    {
      element: (
        <RouteFocusCoordinator>
          <Outlet />
        </RouteFocusCoordinator>
      ),
      children: [
        { path: '/first', element: <FirstPage duplicateMarker={duplicateMarker} /> },
        { path: '/replace', element: <ReplacePage /> },
        { path: '/second', element: <RegisteredPage routeId="second" title="Second page" /> },
        { path: '/deferred', element: <DeferredPage /> },
        { path: '/same-path', element: <SamePathUrlStatePage /> },
      ],
    },
  ], { initialEntries: [initialPath] });
  render(<RouterProvider router={router} />);
  return router;
}

afterEach(() => {
  document.title = '';
});

describe('RouteFocusCoordinator', () => {
  it('leaves focus untouched on a direct initial load', () => {
    renderRouter();
    expect(screen.getByRole('heading', { name: 'First page' })).not.toHaveFocus();
  });

  it('focuses the ready destination H1 after PUSH and restores the stable opener on POP', async () => {
    const router = renderRouter();
    const opener = screen.getByRole('link', { name: 'Open second page' });
    fireEvent.click(opener);

    const secondHeading = await screen.findByRole('heading', { name: 'Second page' });
    await waitFor(() => expect(secondHeading).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    const restoredOpener = await screen.findByRole('link', { name: 'Open second page' });
    await waitFor(() => expect(restoredOpener).toHaveFocus());
  });

  it('waits for route readiness before moving focus', async () => {
    const router = renderRouter();
    await act(async () => {
      await router.navigate('/deferred');
    });
    const heading = await screen.findByRole('heading', { name: 'Deferred page' });
    expect(heading).not.toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: 'Finish loading' }));
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it('focuses the destination H1 for REPLACE navigation', async () => {
    renderRouter('/replace');
    fireEvent.click(screen.getByRole('button', { name: 'Replace with second page' }));
    const heading = await screen.findByRole('heading', { name: 'Second page' });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it('fails closed to the H1 when a route-focus marker is duplicated', async () => {
    const router = renderRouter('/first', true);
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    const firstHeading = await screen.findByRole('heading', { name: 'First page' });
    await waitFor(() => expect(firstHeading).toHaveFocus());
  });

  it('does not treat modifier-click as a same-window transition', () => {
    renderRouter();
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }), { metaKey: true });
    expect(screen.getByRole('heading', { name: 'First page' })).not.toHaveFocus();
    expect(screen.queryByRole('heading', { name: 'Second page' })).not.toBeInTheDocument();
  });

  it('retains control focus for same-path PUSH and REPLACE URL-state updates', async () => {
    renderRouter('/same-path?view=initial');
    const pushControl = screen.getByRole('button', { name: 'Push query state' });
    pushControl.focus();
    fireEvent.click(pushControl);
    expect(screen.getByTestId('same-path-search')).toHaveTextContent('?view=pushed');
    await flushRouteFocusFrames();
    expect(pushControl).toHaveFocus();

    const replaceControl = screen.getByRole('button', { name: 'Replace query state' });
    replaceControl.focus();
    fireEvent.click(replaceControl);
    expect(screen.getByTestId('same-path-search')).toHaveTextContent('?view=replaced');
    await flushRouteFocusFrames();
    expect(replaceControl).toHaveFocus();
    expect(screen.getByRole('heading', { name: 'Same path page' })).not.toHaveFocus();
  });

  it('restores a stable opener on same-path POP without using the H1 fallback', async () => {
    const router = renderRouter('/same-path?view=initial');
    const pushControl = screen.getByRole('button', { name: 'Push query state' });
    pushControl.focus();
    fireEvent.click(pushControl);
    await flushRouteFocusFrames();

    const replaceControl = screen.getByRole('button', { name: 'Replace query state' });
    replaceControl.focus();
    await act(async () => {
      await router.navigate(-1);
    });

    expect(screen.getByTestId('same-path-search')).toHaveTextContent('?view=initial');
    await waitFor(() => expect(pushControl).toHaveFocus());
    expect(screen.getByRole('heading', { name: 'Same path page' })).not.toHaveFocus();
  });
});
