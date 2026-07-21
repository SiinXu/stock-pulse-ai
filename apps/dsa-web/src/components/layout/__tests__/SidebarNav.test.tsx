import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
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

  it('keeps the screening navigation item discoverable while AlphaSift is disabled', () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '选股' })).toHaveAttribute('href', '/screening');
  });

  it('shows the screening navigation item when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('link', { name: '选股' })).toHaveAttribute('href', '/screening');
  });

  it('places screening directly after chat when AlphaSift is enabled', async () => {
    mockGetAlphaSiftStatus.mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    await screen.findByRole('link', { name: '选股' });
    const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
    expect(hrefs.slice(0, 5)).toEqual(['/', '/chat', '/screening', '/portfolio', '/decision-signals']);
  });

  it('keeps the screening navigation item stable after config save events', () => {
    mockGetAlphaSiftStatus
      .mockResolvedValueOnce({ enabled: false, available: false, installSpecIsDefault: false })
      .mockResolvedValueOnce({ enabled: true, available: false, installSpecIsDefault: false });

    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '选股' })).toHaveAttribute('href', '/screening');
    window.dispatchEvent(new Event('dsa-system-config-changed'));
    expect(screen.getByRole('link', { name: '选股' })).toHaveAttribute('href', '/screening');
  });

  it('shows the shared completion badge only when chat completion is pending', () => {
    completionBadgeState.value = true;

    const { rerender } = render(
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('chat-completion-badge')).toBeInTheDocument();
    expect(screen.getByLabelText('问股有新消息')).toBeInTheDocument();

    completionBadgeState.value = false;
    rerender(
      <MemoryRouter initialEntries={['/chat']}>
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
        menuLayout: 'horizontal',
        wrapperClassName: 'w-full',
        triggerClassName: expect.stringContaining('h-11'),
      }),
    );
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

    const chatLink = screen.getByRole('link', { name: '问股' });
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

  it('shows shared tooltips for compact icon-only navigation controls', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed onToggleCollapse={vi.fn()} />
      </MemoryRouter>,
    );

    const search = screen.getByRole('button', { name: '搜索' });
    search.focus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('搜索');
    search.blur();
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());

    const home = screen.getByRole('link', { name: '首页' });
    home.focus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('首页');
  });

  it('renders stable, unique route focus markers from the navigation descriptor', () => {
    render(
      <MemoryRouter initialEntries={['/alerts']}>
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

  it('renders the alerts navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={['/alerts']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const alertsLink = screen.getByRole('link', { name: '告警' });
    expect(alertsLink).toHaveAttribute('href', '/alerts');
    expect(alertsLink).toHaveClass('font-medium');
  });

  it('renders the AI signals navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={['/decision-signals']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const signalsLink = screen.getByRole('link', { name: 'AI 建议' });
    expect(signalsLink).toHaveAttribute('href', '/decision-signals');
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
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '退出' }));

    expect(await screen.findByRole('heading', { name: '退出登录' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认退出' }));
    expect(mockLogout).toHaveBeenCalled();
  });
});
