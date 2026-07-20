import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { Shell } from '../Shell';

const DESKTOP_SIDEBAR_QUERY = '(min-width: 1024px)';
const COMPACT_SIDEBAR_QUERY = '(min-width: 1024px) and (max-width: 1279px)';
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'dsa-sidebar-collapsed';
const mockLogout = vi.fn().mockResolvedValue(undefined);
const mediaMatches = new Map<string, boolean>();
const mediaListeners = new Map<string, Set<(event: MediaQueryListEvent) => void>>();

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: true,
    logout: mockLogout,
  }),
}));

vi.mock('../../../stores/agentChatStore', () => ({
  useAgentChatStore: (selector: (state: { completionBadge: boolean }) => unknown) =>
    selector({ completionBadge: true }),
}));

function createMediaQueryList(query: string): MediaQueryList {
  const listeners = mediaListeners.get(query) ?? new Set();
  mediaListeners.set(query, listeners);
  return {
    get matches() {
      return mediaMatches.get(query) ?? false;
    },
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: (_type: string, listener: EventListenerOrEventListenerObject | null) => {
      if (typeof listener === 'function') {
        listeners.add(listener as (event: MediaQueryListEvent) => void);
      }
    },
    removeEventListener: (_type: string, listener: EventListenerOrEventListenerObject | null) => {
      if (typeof listener === 'function') {
        listeners.delete(listener as (event: MediaQueryListEvent) => void);
      }
    },
    dispatchEvent: vi.fn(),
  } as MediaQueryList;
}

function setMediaMatch(query: string, matches: boolean): void {
  mediaMatches.set(query, matches);
  const event = { matches, media: query } as MediaQueryListEvent;
  mediaListeners.get(query)?.forEach((listener) => listener(event));
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <ThemeProvider>
        <Shell>
          <button type="button">page content</button>
        </Shell>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn((query: string) => createMediaQueryList(query)),
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  mediaMatches.clear();
  mediaListeners.clear();
  localStorage.removeItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
});

describe('Shell', () => {
  it('renders the shared navigation, profile controls, and completion badge', () => {
    renderShell();

    expect(screen.getByRole('link', { name: '问股' })).toBeInTheDocument();
    expect(screen.getByTestId('chat-completion-badge')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'StockPulse' })).toBeInTheDocument();
    expect(screen.getByText('page content')).toBeInTheDocument();
  });

  it('uses an unframed application main instead of an outer card surface', () => {
    renderShell();

    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('data-shell-main', 'true');
  });

  it('keeps one mobile navigation control, the full brand, and restores focus after Escape', () => {
    const { container } = renderShell();

    const mobileHeader = container.querySelector('[data-shell-mobile-header]');
    expect(mobileHeader).not.toBeNull();
    expect(within(mobileHeader as HTMLElement).getAllByRole('button')).toHaveLength(1);
    expect(within(mobileHeader as HTMLElement).getByText('StockPulse')).toBeInTheDocument();
    const openers = screen.getAllByRole('button', { name: '打开导航菜单' });
    expect(openers).toHaveLength(1);
    const opener = openers[0];
    expect(opener).toHaveAttribute('data-control', 'icon-button');
    expect(opener).toHaveAttribute('data-route-focus-key', 'shell:mobile-navigation');
    opener.focus();
    fireEvent.click(opener);

    const drawer = screen.getByRole('dialog', { name: '导航菜单' });
    expect(opener).not.toHaveAttribute('data-route-focus-key');
    expect(within(drawer).getByRole('link', { name: '问股' })).toHaveAttribute(
      'data-route-focus-key',
      'shell-nav-mobile:chat',
    );
    fireEvent.keyDown(drawer, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('moves the selected mobile route marker onto the persistent Drawer opener', () => {
    renderShell();
    const opener = screen.getByRole('button', { name: '打开导航菜单' });
    fireEvent.click(opener);
    const drawer = screen.getByRole('dialog', { name: '导航菜单' });
    fireEvent.click(within(drawer).getByRole('link', { name: '首页' }));

    expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument();
    expect(opener).toHaveAttribute('data-route-focus-key', 'shell-nav-mobile:home');
  });

  it('closes mobile navigation and moves focus to the active desktop route at the breakpoint', async () => {
    renderShell();
    const opener = screen.getByRole('button', { name: '打开导航菜单' });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('dialog', { name: '导航菜单' })).toBeInTheDocument();

    act(() => setMediaMatch(DESKTOP_SIDEBAR_QUERY, true));

    expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('link', { name: '问股' })).toHaveFocus());
  });

  it('does not move content focus when the desktop breakpoint changes with navigation closed', async () => {
    renderShell();
    const pageAction = screen.getByRole('button', { name: 'page content' });
    pageAction.focus();

    act(() => setMediaMatch(DESKTOP_SIDEBAR_QUERY, true));

    await waitFor(() => expect(pageAction).toHaveFocus());
  });

  it('forces a stable compact rail at 1024-1279 without overwriting the saved preference', () => {
    setMediaMatch(COMPACT_SIDEBAR_QUERY, true);
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, '0');
    const { container } = renderShell();

    expect(container.querySelector('[data-shell-sidebar]')).toHaveAttribute(
      'data-shell-sidebar-mode',
      'compact',
    );
    expect(screen.queryByRole('button', { name: '展开侧边栏' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '折叠侧边栏' })).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe('0');
  });

  it('restores the persisted desktop expansion control outside the compact range', () => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, '1');
    const { container } = renderShell();
    const sidebar = container.querySelector('[data-shell-sidebar]');

    expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'compact');
    fireEvent.click(screen.getByRole('button', { name: '展开侧边栏' }));

    expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'expanded');
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe('0');
    expect(screen.getAllByText('StockPulse').length).toBeGreaterThan(0);
  });

  it('shows a confirmation dialog before logout', async () => {
    renderShell();

    fireEvent.click(screen.getByRole('button', { name: '退出' }));

    expect(await screen.findByRole('heading', { name: '退出登录' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认退出' }));
    expect(mockLogout).toHaveBeenCalled();
  });
});
