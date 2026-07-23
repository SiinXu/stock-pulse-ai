import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { APP_ROUTE_PATHS, LEGACY_ROUTE_PATHS } from '../../../routing/routes';
import { recordSessionLocation } from '../../../utils/sessionContinuity';
import { SidebarNav } from '../SidebarNav';

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

const mockLogout = vi.fn().mockResolvedValue(undefined);
const mockGetAlphaSiftStatus = vi.fn().mockResolvedValue({ enabled: false, available: false, installSpecIsDefault: false });
const mockThemeToggle = vi.fn(({ collapsed }: { collapsed?: boolean }) => (
  <button type="button">{collapsed ? '切换主题(折叠)' : '切换主题'}</button>
));

const completionBadgeState = { value: true };

function ClearPortfolioStateHarness() {
  const navigate = useNavigate();
  return (
    <>
      <SidebarNav />
      <button type="button" onClick={() => navigate(APP_ROUTE_PATHS.portfolio)}>All accounts</button>
    </>
  );
}

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: true,
    logout: mockLogout,
  }),
}));

vi.mock('../../../stores/agentChatStore', () => ({
  useAgentChatStore: (selector: (state: { completionBadge: boolean }) => unknown) =>
    selector({ completionBadge: completionBadgeState.value }),
}));

vi.mock('../../../api/alphasift', () => ({
  ALPHASIFT_CONFIG_CHANGED_EVENT: 'alphasift-config-changed',
  SYSTEM_CONFIG_CHANGED_EVENT: 'dsa-system-config-changed',
  alphasiftApi: {
    getStatus: () => mockGetAlphaSiftStatus(),
  },
}));

vi.mock('../../theme/ThemeToggle', () => ({
  ThemeToggle: (props: { collapsed?: boolean }) => mockThemeToggle(props),
}));

describe('SidebarNav', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('keeps icon-only collapse and search controls at least 44px square', () => {
    const onToggleCollapse = vi.fn();
    const { rerender } = render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav onToggleCollapse={onToggleCollapse} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: '折叠侧边栏' })).toHaveClass('h-11', 'w-11');
    expect(screen.getByRole('button', { name: '搜索' })).toHaveClass('min-h-11');

    rerender(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed onToggleCollapse={onToggleCollapse} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: '展开侧边栏' })).toHaveClass('h-11', 'w-11');
    expect(screen.getByRole('button', { name: '搜索' })).toHaveClass('h-11', 'w-11');
    expect(screen.getByRole('button', { name: 'StockPulse' })).toHaveClass('h-11', 'w-11');
  });

  it('keeps the compact brand persistent when the rail cannot expand', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );

    expect(container.querySelector('[data-shell-brand-behavior]')).toHaveAttribute(
      'data-shell-brand-behavior',
      'persistent',
    );
    expect(container.querySelector('[data-shell-brand-mark]')).toBeVisible();
    expect(screen.queryByRole('button', { name: '展开侧边栏' })).not.toBeInTheDocument();
  });

  it('keeps Discover nested under Research while AlphaSift is disabled', () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '发现' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
  });

  it('carries the current stock into stock-aware navigation destinations', () => {
    render(
      <MemoryRouter initialEntries={['/stocks/AAPL']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '首页' })).toHaveAttribute('href', '/?stock=AAPL');
    expect(screen.getByRole('link', { name: 'Agent' })).toHaveAttribute('href', `${APP_ROUTE_PATHS.agent}?stock=AAPL`);
    expect(screen.getByRole('link', { name: 'AI 建议' })).toHaveAttribute('href', `${APP_ROUTE_PATHS.decisionSignals}?stock=AAPL`);
    expect(screen.getByRole('link', { name: '回测' })).toHaveAttribute('href', `${APP_ROUTE_PATHS.researchBacktest}?code=AAPL`);
  });

  it('restores destination-specific state from the current tab session', () => {
    recordSessionLocation(`${APP_ROUTE_PATHS.portfolio}?account=12`);
    recordSessionLocation(`${APP_ROUTE_PATHS.researchDiscover}?strategy=quality&count=20`);

    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.settings]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '组合' })).toHaveAttribute('href', `${APP_ROUTE_PATHS.portfolio}?account=12`);
    expect(screen.getByRole('link', { name: '发现' }))
      .toHaveAttribute('href', `${APP_ROUTE_PATHS.researchDiscover}?strategy=quality&count=20`);
  });

  it('does not resurrect destination state after the current route clears it', async () => {
    recordSessionLocation(`${APP_ROUTE_PATHS.portfolio}?account=12`);
    render(
      <MemoryRouter initialEntries={[`${APP_ROUTE_PATHS.portfolio}?account=12`]}>
        <ClearPortfolioStateHarness />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '组合' })).toHaveAttribute('href', `${APP_ROUTE_PATHS.portfolio}?account=12`);
    fireEvent.click(screen.getByRole('button', { name: 'All accounts' }));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: '组合' })).toHaveAttribute('href', APP_ROUTE_PATHS.portfolio);
    });
  });

  it('shows the Discover navigation item when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('link', { name: '发现' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
  });

  it('renders the grouped domain order when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    await screen.findByRole('link', { name: '发现' });
    const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
    expect(hrefs.slice(0, 9)).toEqual([
      APP_ROUTE_PATHS.home,
      APP_ROUTE_PATHS.decisionSignals,
      APP_ROUTE_PATHS.alerts,
      APP_ROUTE_PATHS.researchMarket,
      APP_ROUTE_PATHS.researchMarket,
      APP_ROUTE_PATHS.researchDiscover,
      APP_ROUTE_PATHS.researchBacktest,
      APP_ROUTE_PATHS.portfolio,
      APP_ROUTE_PATHS.agent,
    ]);
  });

  it('collapses and expands secondary groups with accessible disclosure controls', () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.home]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    for (const name of ['首页', '研究']) {
      const groupLink = screen.getByRole('link', { name });
      expect(groupLink).not.toHaveAttribute('aria-expanded');
      expect(groupLink.querySelectorAll('svg')).toHaveLength(1);
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('button', { name })).toHaveClass('h-11', 'w-11');
    }
    expect(screen.getByRole('link', { name: '大盘复盘' })).toBeVisible();
    expect(screen.getByRole('link', { name: '发现' })).toBeVisible();

    const researchToggle = screen.getByRole('button', { name: '研究' });
    fireEvent.click(researchToggle);
    expect(researchToggle).toHaveAttribute('aria-expanded', 'false');
    expect(researchToggle).not.toHaveAttribute('aria-controls');
    expect(screen.queryByRole('link', { name: '大盘复盘' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '发现' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AI 建议' })).toBeVisible();

    fireEvent.click(researchToggle);
    expect(researchToggle).toHaveAttribute('aria-expanded', 'true');
    expect(researchToggle).toHaveAttribute('aria-controls', 'shell-nav-research-children');
    expect(screen.getByRole('link', { name: '大盘复盘' })).toBeVisible();
    expect(screen.getByRole('link', { name: '发现' })).toBeVisible();
  });

  it('keeps the Discover navigation item stable after config save events', () => {
    mockGetAlphaSiftStatus
      .mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false })
      .mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '发现' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
    window.dispatchEvent(new Event('dsa-system-config-changed'));
    expect(screen.getByRole('link', { name: '发现' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
  });

  it('shows the shared completion badge only when chat completion is pending', () => {
    completionBadgeState.value = true;

    const { rerender } = render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.agent]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('chat-completion-badge')).toBeInTheDocument();
    expect(screen.getByLabelText('问股有新消息')).toBeInTheDocument();

    completionBadgeState.value = false;
    rerender(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.agent]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('chat-completion-badge')).not.toBeInTheDocument();
  });

  it('moves theme and language controls into the collapsed profile menu', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );

    const profileTrigger = screen.getByRole('button', { name: 'StockPulse' });
    expect(profileTrigger).toHaveAttribute('aria-haspopup', 'dialog');
    fireEvent.click(profileTrigger);
    const profileDialog = screen.getByRole('dialog', { name: 'StockPulse' });
    expect(mockThemeToggle).toHaveBeenCalledWith(
      expect.objectContaining({
        wrapperClassName: 'w-full',
        triggerClassName: expect.stringContaining('h-11'),
      }),
    );
    expect(mockThemeToggle.mock.calls.at(-1)?.[0]).not.toHaveProperty('menuLayout');
    expect(within(profileDialog).getByRole('button', { name: '切换主题' })).toBeInTheDocument();
    const languageControl = within(profileDialog).getByTestId('ui-language-selector');
    expect(within(languageControl).getByRole('combobox', { name: '切换界面语言' })).toBeInTheDocument();
    fireEvent.click(within(languageControl).getByRole('combobox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('keeps modifier activation in the current navigation surface', () => {
    const onNavigate = vi.fn();
    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav
          onNavigate={onNavigate}
          focusKeyPrefix="shell-nav-mobile"
          returnFocusKey="shell:mobile-navigation"
        />
      </MemoryRouter>,
    );

    const chatLink = screen.getByRole('link', { name: 'Agent' });
    expect(chatLink).toHaveAttribute('data-route-focus-return-key', 'shell:mobile-navigation');
    const preventNativeNavigation = (event: MouseEvent) => event.preventDefault();
    document.addEventListener('click', preventNativeNavigation);
    try {
      for (const modifier of [
        { metaKey: true },
        { ctrlKey: true },
        { shiftKey: true },
        { altKey: true },
      ]) {
        fireEvent.click(chatLink, modifier);
      }
      expect(onNavigate).not.toHaveBeenCalled();

      fireEvent.click(chatLink);
    } finally {
      document.removeEventListener('click', preventNativeNavigation);
    }
    expect(onNavigate).toHaveBeenCalledOnce();
    expect(onNavigate).toHaveBeenCalledWith();
  });

  it('shows grouped flyouts and shared tooltips for compact navigation controls', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <button type="button">Before navigation</button>
        <SidebarNav collapsed onToggleCollapse={vi.fn()} />
      </MemoryRouter>,
    );

    const search = screen.getByRole('button', { name: '搜索' });
    search.focus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('搜索');
    search.blur();
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());

    const research = screen.getByRole('link', { name: '研究' });
    const beforeNavigation = screen.getByRole('button', { name: 'Before navigation' });
    beforeNavigation.focus();
    fireEvent.mouseEnter(research);
    const menu = await screen.findByRole('menu', { name: '研究' });
    expect(within(menu).getByRole('menuitem', { name: '大盘复盘' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchMarket);
    expect(within(menu).getByRole('menuitem', { name: '发现' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
    expect(research).toHaveAttribute('aria-expanded', 'true');
    expect(beforeNavigation).toHaveFocus();
  });

  it('keeps a compact group open across the hover bridge and closes after leaving it', async () => {
    vi.useFakeTimers();
    try {
      render(
        <MemoryRouter initialEntries={[APP_ROUTE_PATHS.home]}>
          <SidebarNav collapsed />
        </MemoryRouter>,
      );

      const research = screen.getByRole('link', { name: '研究' });
      fireEvent.mouseEnter(research);
      const menu = screen.getByRole('menu', { name: '研究' });
      fireEvent.mouseLeave(research);
      fireEvent.mouseEnter(menu);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(150);
      });
      expect(menu).toBeInTheDocument();

      fireEvent.mouseLeave(menu);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(150);
      });
      expect(screen.queryByRole('menu', { name: '研究' })).not.toBeInTheDocument();
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it('exposes the visible Research child as the only current-page link in expanded and compact navigation', async () => {
    const marketRender = render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.researchMarket]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const researchParent = screen.getByRole('link', { name: '研究' });
    const expandedMarketChild = screen.getByRole('link', { name: '大盘复盘' });
    expect(researchParent).not.toHaveAttribute('aria-current', 'page');
    expect(expandedMarketChild).toHaveAttribute('aria-current', 'page');
    let currentLinks = marketRender.container.querySelectorAll('a[aria-current="page"]');
    expect(currentLinks).toHaveLength(1);
    expect(currentLinks[0]).toBe(expandedMarketChild);
    marketRender.unmount();

    const discoverRender = render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.researchDiscover]}>
        <SidebarNav />
      </MemoryRouter>,
    );
    currentLinks = discoverRender.container.querySelectorAll('a[aria-current="page"]');
    expect(currentLinks).toHaveLength(1);
    expect(currentLinks[0]).toHaveAttribute('href', APP_ROUTE_PATHS.researchDiscover);
    discoverRender.unmount();

    const compactRender = render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.researchMarket]}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );
    const research = screen.getByRole('link', { name: '研究' });
    fireEvent.mouseEnter(research);
    const menu = await screen.findByRole('menu', { name: '研究' });
    const compactMarketChild = within(menu).getByRole('menuitem', { name: '大盘复盘' });
    expect(research).not.toHaveAttribute('aria-current', 'page');
    expect(compactMarketChild).toHaveAttribute('aria-current', 'page');
    currentLinks = document.querySelectorAll('a[aria-current="page"]');
    expect(currentLinks).toHaveLength(1);
    expect(currentLinks[0]).toBe(compactMarketChild);
    compactRender.unmount();
  });

  it('opens compact groups with ArrowRight and restores the trigger with ArrowLeft or Escape', async () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.home]}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );

    const research = screen.getByRole('link', { name: '研究' });
    research.focus();
    fireEvent.keyDown(research, { key: 'ArrowRight' });

    let menu = await screen.findByRole('menu', { name: '研究' });
    const firstItem = within(menu).getByRole('menuitem', { name: '大盘复盘' });
    await waitFor(() => expect(firstItem).toHaveFocus());
    fireEvent.keyDown(firstItem, { key: 'ArrowLeft' });
    await waitFor(() => expect(screen.queryByRole('menu', { name: '研究' })).not.toBeInTheDocument());
    await waitFor(() => expect(research).toHaveFocus());

    fireEvent.keyDown(research, { key: 'ArrowRight' });
    menu = await screen.findByRole('menu', { name: '研究' });
    await waitFor(() => expect(within(menu).getByRole('menuitem', { name: '大盘复盘' })).toHaveFocus());
    fireEvent.keyDown(menu, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu', { name: '研究' })).not.toBeInTheDocument());
    await waitFor(() => expect(research).toHaveFocus());
  });

  it('renders stable, unique route focus markers from the navigation descriptor', () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.alerts]}>
        <SidebarNav focusKeyPrefix="shell-nav-desktop" />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: '搜索' })).toHaveAttribute(
      'data-route-focus-key',
      'shell-nav-desktop:search',
    );
    expect(screen.getByRole('link', { name: '首页' })).toHaveAttribute(
      'data-route-focus-key',
      'shell-nav-desktop:home',
    );
    expect(screen.getByRole('link', { name: '告警' })).toHaveAttribute(
      'data-route-focus-key',
      'shell-nav-desktop:alerts',
    );
    screen.getAllByRole('link').forEach((link) => expect(link).toHaveClass('shrink-0'));

    const markers = Array.from(document.querySelectorAll('[data-route-focus-key]'))
      .map((element) => element.getAttribute('data-route-focus-key'));
    expect(new Set(markers).size).toBe(markers.length);
  });

  it('keeps Usage nested under Settings instead of exposing a legacy sidebar entry', () => {
    const { container } = render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.settings]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link', { name: '用量' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '设置' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.settings);
    expect(container.querySelector(`a[href="${LEGACY_ROUTE_PATHS.usage}"]`)).toBeNull();
  });

  it('renders the alerts navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.alerts]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const alertsLink = screen.getByRole('link', { name: '告警' });
    expect(alertsLink).toHaveAttribute('href', APP_ROUTE_PATHS.alerts);
    expect(alertsLink).toHaveClass('font-medium');
  });

  it('renders the AI signals navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.decisionSignals]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const signalsLink = screen.getByRole('link', { name: 'AI 建议' });
    expect(signalsLink).toHaveAttribute('href', APP_ROUTE_PATHS.decisionSignals);
    expect(signalsLink).toHaveClass('font-medium');
  });

  it('does not expose the component playground in product navigation', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(container.querySelector('a[href="/playground"]')).toBeNull();
  });

  it('opens the logout confirmation and confirms logout', async () => {
    render(
      <MemoryRouter initialEntries={[`${APP_ROUTE_PATHS.agent}?session=private&stock=AAPL&recordId=9`]}>
        <SidebarNav />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '退出' }));

    expect(await screen.findByRole('heading', { name: '退出登录' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认退出' }));
    expect(mockLogout).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: '退出登录' })).not.toBeInTheDocument();
    });
  });
});
