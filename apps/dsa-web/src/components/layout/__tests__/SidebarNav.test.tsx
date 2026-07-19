import { fireEvent, render, screen, within } from '@testing-library/react';
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

    fireEvent.click(screen.getByRole('button', { name: 'StockPulse' }));
    expect(mockThemeToggle).toHaveBeenCalledWith(
      expect.objectContaining({ menuLayout: 'horizontal', wrapperClassName: 'w-full' }),
    );
    expect(screen.getByRole('button', { name: '切换主题' })).toBeInTheDocument();
    const languageControl = screen.getByTestId('ui-language-selector');
    expect(within(languageControl).getByRole('combobox', { name: '切换界面语言' })).toBeInTheDocument();
    fireEvent.click(within(languageControl).getByRole('combobox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
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
