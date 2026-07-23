import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import * as AuthContext from './contexts/AuthContext';
import {
  APP_ROUTE_PATHS,
  LEGACY_ROUTE_PATHS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
} from './routing/routes';
import { recordSessionLocation } from './utils/sessionContinuity';
import { UI_LANGUAGE_STORAGE_KEY } from './utils/uiLanguage';

type AuthState = ReturnType<typeof AuthContext.useAuth>;

const { chatPageShouldThrow, setCurrentRoute, useAgentChatStoreMock } = vi.hoisted(() => {
  const setCurrentRoute = vi.fn();
  const chatPageShouldThrow = { value: false };
  const state = { completionBadge: false };
  const useAgentChatStoreMock = Object.assign(
    vi.fn((selector?: (value: typeof state) => unknown) => (selector ? selector(state) : state)),
    { getState: () => ({ setCurrentRoute }) },
  );
  return { chatPageShouldThrow, setCurrentRoute, useAgentChatStoreMock };
});

vi.mock('./contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: vi.fn(),
}));

vi.mock('./stores/agentChatStore', () => ({
  useAgentChatStore: useAgentChatStoreMock,
}));

vi.mock('./pages/HomePage', () => ({
  default: () => <div data-testid="home-page">Home</div>,
}));

vi.mock('./pages/MarketReviewPage', () => ({
  default: () => <div data-testid="market-review-page">Market review</div>,
}));

vi.mock('./pages/StockScreeningPage', () => ({
  default: () => <div data-testid="screening-page">Screening</div>,
}));

vi.mock('./pages/ChatPage', () => ({
  default: () => {
    if (chatPageShouldThrow.value) {
      throw new Error('chunk load failed');
    }
    return <div data-testid="chat-page">Chat</div>;
  },
}));

vi.mock('./pages/PortfolioPage', () => ({
  default: () => <div data-testid="portfolio-page">Portfolio</div>,
}));

vi.mock('./pages/DecisionSignalsPage', () => ({
  default: () => <div data-testid="decision-signals-page">Decision signals</div>,
}));

vi.mock('./pages/BacktestPage', () => ({
  default: () => <div data-testid="backtest-page">Backtest</div>,
}));

vi.mock('./pages/AlertsPage', () => ({
  default: () => <div data-testid="alerts-page">Alerts</div>,
}));

vi.mock('./pages/SettingsPage', () => ({
  default: () => <div data-testid="settings-page">Settings</div>,
}));

vi.mock('./pages/NotFoundPage', () => ({
  default: () => <div data-testid="not-found-page">Not Found</div>,
}));

vi.mock('./pages/LoginPage', () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));

vi.mock('./playground/ComponentPlaygroundPage', () => ({
  default: () => <div data-testid="playground-page">Playground</div>,
}));

vi.mock('./playground/PlaygroundRenderPage', () => ({
  default: () => <div data-testid="playground-render-page">Playground render</div>,
}));

function makeAuthState(overrides: Partial<AuthState> = {}): AuthState {
  return {
    authEnabled: false,
    loggedIn: false,
    passwordSet: false,
    passwordChangeable: false,
    setupState: 'no_password',
    isLoading: false,
    loadError: null,
    logoutRedirectPending: false,
    login: vi.fn().mockResolvedValue({ success: true }),
    changePassword: vi.fn().mockResolvedValue({ success: true }),
    logout: vi.fn().mockResolvedValue(undefined),
    refreshStatus: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  chatPageShouldThrow.value = false;
  window.history.pushState({}, '', '/');
  localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');
  sessionStorage.clear();
  vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState());
});

describe('App routing behavior', () => {
  it('shows loading fallback while auth status is initializing', () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({ isLoading: true }));

    const { container } = render(<App />);

    expect(container.querySelector('.border-t-primary')).toBeInTheDocument();
  });

  it('redirects protected routes to login when auth is enabled but user is not logged in', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/portfolio');

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(window.location.search).toBe('?redirect=%2Fportfolio');
  });

  it('preserves explicit Discover default ownership in an authentication redirect', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    const discoverSearch = new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
    }).toString();
    const discoverHref = `${APP_ROUTE_PATHS.researchDiscover}?${discoverSearch}`;
    window.history.pushState({}, '', discoverHref);

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('redirect')).toBe(discoverHref);
  });

  it('redirects an explicit logout to plain login without retaining workflow identity', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
      logoutRedirectPending: true,
    }));
    window.history.pushState({}, '', '/chat?session=private&stock=AAPL&recordId=9');

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(window.location.search).toBe('');
  });

  it('keeps the hidden playground behind the existing authentication boundary', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/playground?component=modal&scenario=interactive');

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(window.location.search).toContain('redirect=');
    expect(decodeURIComponent(new URLSearchParams(window.location.search).get('redirect') || ''))
      .toBe('/playground?component=modal&scenario=interactive');
  });

  it('renders the hidden playground without the product shell after authentication', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/playground');

    render(<App />);

    expect(await screen.findByTestId('playground-page')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument();
  });

  it('renders the current route page after auth is ready', async () => {
    window.history.pushState({}, '', '/chat');

    render(<App />);

    expect(await screen.findByTestId('chat-page')).toBeInTheDocument();
    expect(setCurrentRoute).toHaveBeenCalledWith('/chat');
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it('restores the last tab-scoped route state on a bare reload', async () => {
    recordSessionLocation('/portfolio?account=4');
    window.history.pushState({}, '', '/portfolio');

    render(<App />);

    expect(await screen.findByTestId('portfolio-page')).toBeInTheDocument();
    expect(window.location.search).toBe('?account=4');
  });

  it('does not replace an invalid-link fallback with stale session state', async () => {
    recordSessionLocation('/?stock=AAPL&workspace=watchlist');
    window.history.pushState({}, '', '/stocks/%3Cscript%3E');

    render(<App />);

    expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/');
    expect(window.location.search).toBe('');
  });

  it('redirects the legacy usage route into Settings with query and hash preserved', async () => {
    window.history.pushState(
      {},
      '',
      `${LEGACY_ROUTE_PATHS.usage}?period=today&section=legacy#breakdown`,
    );

    render(<App />);

    expect(await screen.findByTestId('settings-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe(APP_ROUTE_PATHS.settings);
    expect(window.location.hash).toBe('#breakdown');
    const searchParams = new URLSearchParams(window.location.search);
    expect(searchParams.get('period')).toBe('today');
    expect(searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section))
      .toBe(SETTINGS_SECTION_IDS.usage);
    expect(setCurrentRoute).toHaveBeenLastCalledWith(APP_ROUTE_PATHS.settings);
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it('routes the canonical market-review path after auth is ready', async () => {
    window.history.pushState({}, '', APP_ROUTE_PATHS.researchMarket);

    render(<App />);

    expect(await screen.findByTestId('market-review-page')).toBeInTheDocument();
    expect(setCurrentRoute).toHaveBeenLastCalledWith(APP_ROUTE_PATHS.researchMarket);
  });

  it.each([
    [LEGACY_ROUTE_PATHS.screening, APP_ROUTE_PATHS.researchDiscover, 'screening-page'],
    [LEGACY_ROUTE_PATHS.backtest, APP_ROUTE_PATHS.researchBacktest, 'backtest-page'],
  ])('redirects %s to %s while preserving query and hash', async (legacyPath, canonicalPath, testId) => {
    window.history.pushState({}, '', `${legacyPath}?keep=yes#results`);

    render(<App />);

    expect(await screen.findByTestId(testId)).toBeInTheDocument();
    expect(window.location.pathname).toBe(canonicalPath);
    expect(window.location.search).toBe('?keep=yes');
    expect(window.location.hash).toBe('#results');
    await waitFor(() => expect(setCurrentRoute).toHaveBeenLastCalledWith(canonicalPath));
  });

  it('routes /decision-signals to the AI signals page after auth is ready', async () => {
    window.history.pushState({}, '', '/decision-signals');

    render(<App />);

    expect(await screen.findByTestId('decision-signals-page')).toBeInTheDocument();
    expect(setCurrentRoute).toHaveBeenCalledWith('/decision-signals');
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it('redirects authenticated login visits back to the home page', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/login');

    render(<App />);

    expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('preserves the deep link when an authenticated user lands on /login with a redirect', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/login?redirect=%2Fsettings%3Fsection%3Dai_models');

    render(<App />);

    expect(await screen.findByTestId('settings-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe(APP_ROUTE_PATHS.settings);
    expect(window.location.search).toBe('?section=ai_models');
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it.each([
    {
      name: 'canonical custom Discover state',
      href: `${APP_ROUTE_PATHS.researchDiscover}?${new URLSearchParams({
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'custom_strategy_alpha',
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '17',
      }).toString()}#details`,
    },
    {
      name: 'legacy explicit default Discover state',
      href: `${LEGACY_ROUTE_PATHS.screening}?${new URLSearchParams({
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      }).toString()}#details`,
    },
    {
      name: 'legacy malformed Discover state',
      href: `${LEGACY_ROUTE_PATHS.screening}?${new URLSearchParams({
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: '<bad>',
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '999',
      }).toString()}#details`,
      sanitizedHref: `${LEGACY_ROUTE_PATHS.screening}?${new URLSearchParams({
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      }).toString()}#details`,
    },
  ])('encodes the full $name URL for authentication return', async (testCase) => {
    const { href } = testCase;
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', href);

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    const loginUrl = new URL(window.location.href);
    expect(loginUrl.pathname).toBe(APP_ROUTE_PATHS.login);
    expect(loginUrl.searchParams.get('redirect')).toBe(
      'sanitizedHref' in testCase ? testCase.sanitizedHref : href,
    );
  });

  it('restores explicit Discover default ownership after authentication', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    const discoverSearch = new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
    }).toString();
    const discoverHref = `${APP_ROUTE_PATHS.researchDiscover}?${discoverSearch}#details`;
    const loginSearch = new URLSearchParams({ redirect: discoverHref }).toString();
    window.history.pushState({}, '', `${APP_ROUTE_PATHS.login}?${loginSearch}`);

    render(<App />);

    expect(await screen.findByTestId('screening-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe(APP_ROUTE_PATHS.researchDiscover);
    expect(window.location.search).toBe(`?${discoverSearch}`);
    expect(window.location.hash).toBe('#details');
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('rejects non-relative login redirects and falls back to the home page', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/login?redirect=%2F%2Fevil.example.com');

    render(<App />);

    expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/');
  });

  it('keeps the shell mounted and resets the route boundary after page render errors', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    chatPageShouldThrow.value = true;
    window.history.pushState({}, '', '/chat');

    try {
      render(<App />);

      expect(await screen.findByRole('heading', { name: '页面加载失败' })).toBeInTheDocument();
      expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '重新加载页面' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '返回首页' })).toBeInTheDocument();

      chatPageShouldThrow.value = false;
      fireEvent.click(screen.getByRole('link', { name: '组合' }));

      expect(await screen.findByTestId('portfolio-page')).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: '页面加载失败' })).not.toBeInTheDocument();
    } finally {
      consoleError.mockRestore();
    }
  });
});
