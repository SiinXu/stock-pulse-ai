// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useRef, useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import {
  createMemoryRouter,
  Link,
  Outlet,
  RouterProvider,
  useBlocker,
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

type MarkerMode = 'normal' | 'duplicate' | 'missing' | 'stale' | 'unfocusable';

function FirstPage({
  markerMode,
  blockNavigation,
}: {
  markerMode: () => MarkerMode;
  blockNavigation: () => boolean;
}) {
  const blocker = useBlocker(blockNavigation());
  const mode = markerMode();
  const opener = mode === 'missing' ? (
    <span>Second page opener removed</span>
  ) : mode === 'unfocusable' ? (
    <button type="button" data-route-focus-key="first:second" disabled>
      Open second page
    </button>
  ) : (
    <Link
      to="/second"
      data-route-focus-key={mode === 'stale' ? 'first:stale' : 'first:second'}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey) event.preventDefault();
      }}
    >
      Open second page
    </Link>
  );

  return (
    <RegisteredPage routeId="first" title="First page">
      {opener}
      {mode === 'duplicate'
        ? <Link to="/second" data-route-focus-key="first:second">Duplicate second link</Link>
        : null}
      <Link
        to="/second"
        data-route-focus-key="first:canceled"
        onClick={(event) => event.preventDefault()}
      >
        Cancel second-page navigation
      </Link>
      {blocker.state === 'blocked' ? (
        <div role="dialog" aria-label="Unsaved changes">
          <button type="button" onClick={() => blocker.proceed()}>Proceed</button>
          <button type="button" onClick={() => blocker.reset()}>Stay</button>
        </div>
      ) : null}
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

function renderRouter(
  initialPath = '/first',
  markerMode: () => MarkerMode = () => 'normal',
  blockNavigation: () => boolean = () => false,
) {
  const router = createMemoryRouter([
    {
      element: (
        <RouteFocusCoordinator>
          <Outlet />
        </RouteFocusCoordinator>
      ),
      children: [
        {
          path: '/first',
          element: <FirstPage markerMode={markerMode} blockNavigation={blockNavigation} />,
        },
        { path: '/replace', element: <ReplacePage /> },
        { path: '/previous', element: <RegisteredPage routeId="previous" title="Previous page" /> },
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

  it('preserves an entry opener through repeated Back and Forward POP navigation', async () => {
    const router = renderRouter();
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('link', { name: 'Open second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('link', { name: 'Open second page' })).toHaveFocus());
  });

  it('discards a canceled trigger before a later POP transition', async () => {
    const router = renderRouter('/previous');
    await act(async () => {
      await router.navigate('/first');
    });
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('link', { name: 'Open second page' })).toHaveFocus());

    fireEvent.click(screen.getByRole('link', { name: 'Cancel second-page navigation' }));
    await act(async () => {
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Previous page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => expect(screen.getByRole('link', { name: 'Open second page' })).toHaveFocus());
  });

  it('retains the original trigger while useBlocker waits and later proceeds', async () => {
    const router = renderRouter('/first', () => 'normal', () => true);
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    expect(router.state.location.pathname).toBe('/first');

    const dialog = await screen.findByRole('dialog', { name: 'Unsaved changes' });
    await act(async () => {
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Proceed' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('link', { name: 'Open second page' })).toHaveFocus());
  });

  it('discards the blocked trigger when useBlocker resets the transition', async () => {
    let shouldBlock = true;
    const router = renderRouter('/previous', () => 'normal', () => shouldBlock);
    await act(async () => {
      await router.navigate('/first');
    });
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    const dialog = await screen.findByRole('dialog', { name: 'Unsaved changes' });

    shouldBlock = false;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stay' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Unsaved changes' })).not.toBeInTheDocument());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Previous page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'First page' })).toHaveFocus());
  });

  it('focuses the H1 when PUSH creates a new history key for the same URL', async () => {
    const router = renderRouter();
    const initialKey = router.state.location.key;

    await act(async () => {
      await router.navigate('/first');
    });

    expect(router.state.location.key).not.toBe(initialKey);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'First page' })).toHaveFocus());
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
    const router = renderRouter('/first', () => 'duplicate');
    fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

    await act(async () => {
      await router.navigate(-1);
    });
    const firstHeading = await screen.findByRole('heading', { name: 'First page' });
    await waitFor(() => expect(firstHeading).toHaveFocus());
  });

  it.each<MarkerMode>(['missing', 'stale', 'unfocusable'])(
    'fails closed to the H1 when the saved opener becomes %s',
    async (fallbackMode) => {
      let markerMode: MarkerMode = 'normal';
      const router = renderRouter('/first', () => markerMode);
      fireEvent.click(screen.getByRole('link', { name: 'Open second page' }));
      await waitFor(() => expect(screen.getByRole('heading', { name: 'Second page' })).toHaveFocus());

      markerMode = fallbackMode;
      await act(async () => {
        await router.navigate(-1);
      });

      await waitFor(() => expect(screen.getByRole('heading', { name: 'First page' })).toHaveFocus());
    },
  );

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
