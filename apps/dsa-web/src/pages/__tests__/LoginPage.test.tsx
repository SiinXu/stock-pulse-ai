import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '../LoginPage';

const { connectionState, navigate, useSearchParamsMock, useAuthMock } = vi.hoisted(() => ({
  connectionState: { status: 'local-http' },
  navigate: vi.fn(),
  useSearchParamsMock: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../../hooks', () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock('../../utils/loginConnection', () => ({
  getLoginConnectionStatus: () => connectionState.status,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigate,
    useSearchParams: () => useSearchParamsMock(),
  };
});

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    connectionState.status = 'local-http';
    document.documentElement.className = 'light';
    useSearchParamsMock.mockReturnValue([new URLSearchParams('redirect=%2Fsettings')]);
  });

  it('blocks first-time setup when confirmation does not match', async () => {
    const login = vi.fn();
    useAuthMock.mockReturnValue({
      login,
      passwordSet: false,
      setupState: 'no_password',
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('管理员密码'), { target: { value: 'passwd6' } });
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'passwd7' } });
    fireEvent.click(screen.getByRole('button', { name: '完成设置并登录' }));

    expect(await screen.findByText('两次输入的密码不一致')).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('data-appearance', 'login');
    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('name', 'stockpulse-admin-new-password');
    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('data-appearance', 'login');
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('name', 'stockpulse-admin-new-password-confirmation');
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('autocomplete', 'new-password');
  });

  it('navigates to redirect after a successful login', async () => {
    useAuthMock.mockReturnValue({
      login: vi.fn().mockResolvedValue({ success: true }),
      passwordSet: true,
      setupState: 'enabled',
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('登录密码'), { target: { value: 'passwd6' } });
    fireEvent.click(screen.getByRole('button', { name: '授权进入工作台' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/settings', { replace: true }));
    expect(screen.getByLabelText('登录密码')).toHaveAttribute('data-appearance', 'login');
    expect(screen.getByLabelText('登录密码')).toHaveAttribute('name', 'stockpulse-admin-current-password');
    expect(screen.getByLabelText('登录密码')).toHaveAttribute('autocomplete', 'current-password');
  });

  it('does not override login theme tokens inline so light mode can take effect', () => {
    useAuthMock.mockReturnValue({
      login: vi.fn(),
      passwordSet: true,
      setupState: 'enabled',
    });

    const { container } = render(<LoginPage />);
    const pageRoot = container.firstElementChild as HTMLElement | null;

    expect(pageRoot).not.toBeNull();
    expect(pageRoot?.getAttribute('style') ?? '').not.toContain('--login-bg-main');
  });

  it('presents the current StockPulse brand as an accessible heading', () => {
    useAuthMock.mockReturnValue({
      login: vi.fn(),
      passwordSet: true,
      setupState: 'enabled',
    });

    render(<LoginPage />);

    expect(screen.getByRole('heading', { name: 'StockPulse' })).toBeInTheDocument();
    expect(screen.queryByText('DAILY STOCK')).not.toBeInTheDocument();
    expect(screen.queryByText('Analysis Engine')).not.toBeInTheDocument();
  });

  it.each([
    ['https', '此登录页面使用 HTTPS 加密传输。', false],
    ['local-http', '当前通过本机 HTTP 连接访问；此连接未使用 HTTPS。', false],
    ['insecure-http', '警告：当前连接未使用 HTTPS。登录密码可能在传输中暴露，请改用 HTTPS。', true],
  ] as const)(
    'renders truthful %s transport copy',
    (status, expectedCopy, isWarning) => {
      connectionState.status = status;
      useAuthMock.mockReturnValue({
        login: vi.fn(),
        passwordSet: true,
        setupState: 'enabled',
      });

      render(<LoginPage />);

      const notice = screen.getByText(expectedCopy);
      expect(notice).toHaveAttribute('data-connection-status', status);
      expect(notice).toHaveAttribute('role', isWarning ? 'alert' : 'status');
      if (isWarning) {
        expect(notice).toHaveClass('text-[hsl(var(--color-danger-alert-text))]');
        expect(notice).not.toHaveClass('text-warning');
      }
      expect(screen.queryByText(/StockPulse-V3-TLS/)).not.toBeInTheDocument();
    },
  );
});
