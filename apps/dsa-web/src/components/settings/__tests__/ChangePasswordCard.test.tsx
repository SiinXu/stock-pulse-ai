import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChangePasswordCard } from '../ChangePasswordCard';

const { changePassword, useAuthMock } = vi.hoisted(() => ({
  changePassword: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../../../hooks', () => ({
  useAuth: () => useAuthMock(),
}));

describe('ChangePasswordCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthMock.mockReturnValue({ changePassword });
  });

  it('keeps current, new, and confirmation passwords in distinct browser identities', () => {
    render(<ChangePasswordCard />);

    expect(screen.getByLabelText('当前密码')).toHaveAttribute(
      'name',
      'stockpulse-admin-current-password',
    );
    expect(screen.getByLabelText('当前密码')).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByLabelText('新密码')).toHaveAttribute(
      'name',
      'stockpulse-admin-new-password',
    );
    expect(screen.getByLabelText('新密码')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('确认新密码')).toHaveAttribute(
      'name',
      'stockpulse-admin-new-password-confirmation',
    );
    expect(screen.getByLabelText('确认新密码')).toHaveAttribute('autocomplete', 'new-password');
  });
});
