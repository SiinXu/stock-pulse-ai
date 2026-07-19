import { fireEvent, render, screen } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ConfirmDialog } from '../ConfirmDialog';
import { OVERLAY_Z } from '../overlayZ';

function renderDialog(overrides: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const result = render(
    <UiLanguageProvider>
      <ConfirmDialog
        isOpen
        title="确认操作"
        message="确认继续吗？"
        confirmText="确定"
        cancelText="取消"
        onConfirm={onConfirm}
        onCancel={onCancel}
        {...overrides}
      />
    </UiLanguageProvider>,
  );
  return { onConfirm, onCancel, ...result };
}

describe('ConfirmDialog', () => {
  it('renders above every drawer, navigation, and settings overlay layer', () => {
    renderDialog();

    const root = screen.getByRole('dialog', { name: '确认操作' }).closest<HTMLElement>('[data-overlay-root]');
    expect(root?.style.zIndex).toBe(String(OVERLAY_Z.confirmation));
    expect(OVERLAY_Z.confirmation).toBeGreaterThan(OVERLAY_Z.toast);
    expect(OVERLAY_Z.confirmation).toBeGreaterThan(OVERLAY_Z.tooltip);
    expect(OVERLAY_Z.confirmation).toBeGreaterThan(OVERLAY_Z.dialog);
  });

  it('disables confirm and cancel actions independently', () => {
    const { onConfirm, onCancel } = renderDialog({
      confirmDisabled: true,
      cancelDisabled: true,
    });

    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    fireEvent.click(document.body.lastElementChild as HTMLElement);

    expect(screen.getByRole('button', { name: '确定' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('keeps the default confirm and cancel behavior when not disabled', () => {
    const { onConfirm, onCancel } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('uses the comfortable shared control tier for both actions', () => {
    renderDialog();

    expect(screen.getByRole('button', { name: '确定' })).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByRole('button', { name: '取消' })).toHaveAttribute('data-size', 'comfortable');
  });
});
