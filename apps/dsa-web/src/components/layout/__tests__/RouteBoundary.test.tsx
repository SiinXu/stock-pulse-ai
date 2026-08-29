import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { lazy } from 'react';
import type React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import { RouteOutletBoundary } from '../RouteBoundary';
import { Shell } from '../Shell';

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: false,
    logout: vi.fn().mockResolvedValue(undefined),
  }),
}));

vi.mock('../../../stores/agentChatStore', () => {
  const state = { completionBadge: false };

  return {
    useAgentChatStore: (selector?: (value: typeof state) => unknown) => (
      selector ? selector(state) : state
    ),
  };
});

vi.mock('../../../hooks/useLocalOnlyModeStatus', () => ({
  useLocalOnlyModeStatus: () => ({ status: 'off' }),
}));

describe('RouteOutletBoundary', () => {
  let queryClient: ReturnType<typeof createAppQueryClient>;

  /**
   * The shell header renders the real `NotificationBell`, whose
   * `useUnreadNotifications` hook calls `useQueryClient`. Use the same
   * production factory as `main.tsx` with a fresh client per test.
   */
  beforeEach(() => {
    queryClient = createAppQueryClient();
  });

  afterEach(() => {
    queryClient.clear();
    queryClient.unmount();
  });

  it('catches rejected lazy route imports inside the shell and resets on navigation', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const BrokenLazyRoute = lazy(() => (
      Promise.reject(new Error('chunk load failed')) as Promise<{ default: React.ComponentType }>
    ));

    try {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/chat']}>
            <Routes>
              <Route
                element={(
                  <Shell>
                    <RouteOutletBoundary />
                  </Shell>
                )}
              >
                <Route path="/chat" element={<BrokenLazyRoute />} />
                <Route path="/portfolio" element={<div data-testid="portfolio-page">Portfolio</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument();
      expect(await screen.findByRole('heading', { name: '页面加载失败' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '重新加载页面' })).toHaveAttribute('data-variant', 'primary');
      expect(screen.getByRole('button', { name: '返回首页' })).toHaveAttribute('data-variant', 'secondary');

      fireEvent.click(screen.getByRole('link', { name: '组合' }));

      expect(await screen.findByTestId('portfolio-page')).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: '页面加载失败' })).not.toBeInTheDocument();
    } finally {
      consoleError.mockRestore();
    }
  });
});
