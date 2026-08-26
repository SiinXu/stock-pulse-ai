/**
 * First-chrome measurement for Issue #883 / T26.
 * Isolated so Shell mocks cannot collide with the SSE store contract.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../../components/theme/ThemeProvider';
import { Shell } from '../../components/layout/Shell';
import { flushRuntimePerfReport, recordRuntimePerf } from '../runtimePerfReport';
import { FIRST_CHROME_LANDMARK_BUDGET } from '../runtimeBudgets';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: true,
    logout: vi.fn().mockResolvedValue(undefined),
  }),
}));

vi.mock('../../stores/agentChatStore', () => ({
  useAgentChatStore: (selector: (state: { completionBadge: boolean }) => unknown) =>
    selector({ completionBadge: false }),
}));

vi.mock('../../hooks/useUnreadNotifications', () => ({
  useUnreadNotifications: () => ({
    items: [],
    unreadCount: 0,
    isLoading: false,
    hasError: false,
    hasPartialError: false,
    listFailed: false,
    countFailed: false,
    markFailed: false,
    markAllSeen: async () => undefined,
    refresh: () => undefined,
  }),
}));

vi.mock('../../hooks/useLocalOnlyModeStatus', () => ({
  useLocalOnlyModeStatus: () => ({ status: 'off' }),
}));

vi.mock('../../components/StockAutocomplete', () => ({
  StockAutocomplete: ({ ariaLabel }: { ariaLabel: string }) => <input aria-label={ariaLabel} />,
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: vi.fn().mockResolvedValue({ skills: [], default_skill_id: '' }),
  },
}));

vi.mock('../../api/history', () => ({
  historyApi: {
    search: vi.fn().mockResolvedValue({ query: '', limit: 5, items: [] }),
  },
}));

afterEach(() => {
  flushRuntimePerfReport();
});

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

beforeEach(() => {
  window.localStorage.clear();
});

describe('first-chrome-shell', () => {
  it(`mounts at least ${FIRST_CHROME_LANDMARK_BUDGET} chrome landmarks before heavy widgets`, () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <ThemeProvider>
          <Shell>
            <div data-testid="pending-route">pending</div>
          </Shell>
        </ThemeProvider>
      </MemoryRouter>,
    );

    const landmarks = [
      container.querySelector('[data-shell-sidebar]'),
      container.querySelector('[data-shell-main]'),
      container.querySelector('[data-shell-mobile-header]'),
    ].filter(Boolean).length;
    recordRuntimePerf('first-chrome-shell', landmarks, 'landmarks');
    expect(landmarks).toBeGreaterThanOrEqual(FIRST_CHROME_LANDMARK_BUDGET);
    expect(container.querySelector('[data-testid="pending-route"]')).not.toBeNull();
  });
});
