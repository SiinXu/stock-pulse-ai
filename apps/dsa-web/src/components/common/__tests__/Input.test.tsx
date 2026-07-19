import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Input } from '../Input';

describe('Input', () => {
  it('forwards its native ref and exposes the selected semantic size', () => {
    const ref = createRef<HTMLInputElement>();

    render(<Input ref={ref} aria-label="Search" size="default" />);

    const input = screen.getByRole('textbox', { name: 'Search' });
    expect(ref.current).toBe(input);
    expect(input).toHaveAttribute('data-control', 'input');
    expect(input).toHaveAttribute('data-size', 'default');
    expect(input).not.toHaveAttribute('size');
  });

  it('uses the comfortable semantic size by default', () => {
    render(<Input aria-label="Search" />);

    expect(screen.getByRole('textbox', { name: 'Search' })).toHaveAttribute(
      'data-size',
      'comfortable',
    );
  });

  it('keeps caller data attributes from replacing its semantic contract', () => {
    render(
      <Input
        aria-label="Search"
        data-control="caller-control"
        data-size="caller-size"
        data-appearance="caller-appearance"
      />,
    );

    const input = screen.getByRole('textbox', { name: 'Search' });
    expect(input).toHaveAttribute('data-control', 'input');
    expect(input).toHaveAttribute('data-size', 'comfortable');
    expect(input).toHaveAttribute('data-appearance', 'default');
  });

  it('focuses the native control from its coarse-pointer target frame', () => {
    render(<Input aria-label="Search" />);

    const input = screen.getByRole('textbox', { name: 'Search' });
    fireEvent.pointerDown(input.parentElement as HTMLElement);

    expect(input).toHaveFocus();
  });

  it('wires label and hint text to the input', () => {
    render(<Input label="API Key" hint="Stored locally" name="api_key" />);

    const input = screen.getByLabelText('API Key');
    expect(input).toHaveAttribute('id', 'api_key');
    expect(input).toHaveAttribute('aria-describedby', 'api_key-hint');
    expect(screen.getByText('Stored locally')).toBeInTheDocument();
  });

  it('preserves caller descriptions while appending the active field message', () => {
    render(
      <>
        <p id="shared-context">Shared context</p>
        <Input
          label="API Key"
          error="Required"
          name="api_key"
          aria-describedby="shared-context"
        />
      </>,
    );

    expect(screen.getByLabelText('API Key')).toHaveAttribute(
      'aria-describedby',
      'shared-context api_key-error',
    );
  });

  it('preserves caller styles alongside the error focus variables', () => {
    render(
      <Input
        aria-label="Code"
        error="Required"
        style={{ opacity: 0.75 }}
      />,
    );

    const input = screen.getByRole('textbox', { name: 'Code' });
    expect(input).toHaveStyle({ opacity: '0.75' });
    expect(input.style.getPropertyValue('--input-surface-border-focus')).toBe(
      'hsla(var(--destructive), 0.4)',
    );
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
    expect(input).toHaveAttribute('data-size', 'comfortable');
    expect(toggle).toHaveAttribute('data-size', 'default');
    expect(toggle).toHaveAttribute('data-variant', 'ghost');

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
    expect(input).toHaveAttribute('data-size', 'primary');
    expect(input).toHaveClass('input-appearance-login');
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
  });
});
