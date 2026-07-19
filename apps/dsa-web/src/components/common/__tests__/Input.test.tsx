import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Input } from '../Input';

describe('Input', () => {
  it('keeps the default input at the compact shared height', () => {
    render(<Input aria-label="Search" />);

    expect(screen.getByRole('textbox', { name: 'Search' })).toHaveClass(
      'h-9',
      'min-h-9',
      'min-w-9'
    );
  });

  it('retains the shared minimum height when a caller requests compact visual height', () => {
    render(<Input aria-label="Compact search" className="h-9" />);

    expect(screen.getByRole('textbox', { name: 'Compact search' })).toHaveClass('h-9', 'min-h-9');
  });

  it('wires label and hint text to the input', () => {
    render(<Input label="API Key" hint="Stored locally" name="api_key" />);

    const input = screen.getByLabelText('API Key');
    expect(input).toHaveAttribute('id', 'api_key');
    expect(input).toHaveAttribute('aria-describedby', 'api_key-hint');
    expect(screen.getByText('Stored locally')).toBeInTheDocument();
  });

  it('forwards the native input ref', () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input ref={ref} aria-label="Referenced input" />);

    expect(ref.current).toBe(screen.getByRole('textbox', { name: 'Referenced input' }));
  });

  it('marks the input invalid and shows the error message', () => {
    render(<Input label="Code" error="Required" name="stock_code" />);

    const input = screen.getByLabelText('Code');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('aria-describedby', 'stock_code-error');
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
  });

  it('renders a trailing action when provided', () => {
    render(
      <Input
        label="Password"
        name="password"
        trailingAction={<button type="button">显示</button>}
      />
    );

    expect(screen.getByRole('button', { name: '显示' })).toBeInTheDocument();
  });

  it('renders a key icon and applies leading padding', () => {
    const { container } = render(<Input label="API Key" iconType="key" />);

    expect(container.querySelector('svg')).not.toBeNull();
    expect(screen.getByLabelText('API Key')).toHaveClass('pl-9');
  });

  it('toggles password visibility in uncontrolled mode', () => {
    render(<Input label="密码" type="password" allowTogglePassword />);

    const input = screen.getByLabelText('密码');
    const toggle = screen.getByRole('button', { name: '显示内容' });
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveClass('h-9');
    expect(toggle).toHaveClass('h-9', 'w-9');

    fireEvent.click(toggle);
    expect(input).toHaveAttribute('type', 'text');
  });

  it('supports controlled password visibility', () => {
    const onPasswordVisibleChange = vi.fn();

    render(
      <Input
        label="API Key"
        type="password"
        allowTogglePassword
        passwordVisible
        onPasswordVisibleChange={onPasswordVisibleChange}
      />
    );

    expect(screen.getByLabelText('API Key')).toHaveAttribute('type', 'text');

    fireEvent.click(screen.getByRole('button', { name: '隐藏内容' }));
    expect(onPasswordVisibleChange).toHaveBeenCalledWith(false);
  });

  it('adds localized field context to the password visibility action', () => {
    render(
      <Input
        aria-label="OpenAI API Keys 2"
        type="password"
        allowTogglePassword
        passwordToggleLabel="OpenAI API Keys 2"
      />
    );

    const show = screen.getByRole('button', { name: '显示内容：OpenAI API Keys 2' });
    fireEvent.click(show);
    expect(screen.getByRole('button', { name: '隐藏内容：OpenAI API Keys 2' })).toBeInTheDocument();
  });

  it('supports the login appearance without affecting password toggle behavior', () => {
    render(<Input label="登录密码" type="password" allowTogglePassword appearance="login" />);

    const input = screen.getByLabelText('登录密码');
    expect(input).toHaveAttribute('data-appearance', 'login');
    expect(input).toHaveClass('input-appearance-login');
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
  });
});
