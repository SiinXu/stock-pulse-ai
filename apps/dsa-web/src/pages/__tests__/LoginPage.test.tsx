import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '../LoginPage';

const { navigate, useSearchParamsMock, useAuthMock } = vi.hoisted(() => ({
  navigate: vi.fn(),
  useSearchParamsMock: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../../hooks', () => ({
  useAuth: () => useAuthMock(),
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
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('data-appearance', 'login');
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
    const passwordInput = screen.getByLabelText('登录密码');
    expect(passwordInput).toHaveAttribute('data-appearance', 'login');
    expect(passwordInput).toHaveAttribute('name', 'stockpulse-admin-password');
    expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');
  });

  it('identifies first-time password fields independently from API credentials', () => {
    useAuthMock.mockReturnValue({
      login: vi.fn(),
      passwordSet: false,
      setupState: 'no_password',
    });

    render(<LoginPage />);

    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('name', 'stockpulse-admin-password');
    expect(screen.getByLabelText('管理员密码')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('确认密码')).toHaveAttribute(
      'name',
      'stockpulse-admin-password-confirmation',
    );
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('autocomplete', 'new-password');
  });

  it('describes the default localhost HTTP environment without claiming TLS', () => {
    useAuthMock.mockReturnValue({
      login: vi.fn(),
      passwordSet: true,
      setupState: 'enabled',
    });

    render(<LoginPage />);

    const status = screen.getByText('当前通过本机开发连接访问。');
    expect(status).toHaveAttribute('data-connection-status', 'local');
    expect(screen.queryByText(/StockPulse-V3-TLS/)).not.toBeInTheDocument();
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
});
