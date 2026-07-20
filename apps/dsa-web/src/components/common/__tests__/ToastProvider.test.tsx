// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Modal } from '../Modal';
import { OVERLAY_Z } from '../overlayZ';
import { ToastProvider } from '../ToastProvider';
import { useToast } from '../toastContext';

const Harness = () => {
  const { showToast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => showToast({ title: 'Report ready', tone: 'success', durationMs: 0 })}
      >
        Show toast
      </button>
      <button type="button" onClick={() => setModalOpen(true)}>Open modal</button>
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Report details">
        <p>Report body</p>
      </Modal>
    </>
  );
};

const TimedToastHarness = () => {
  const { showToast } = useToast();
  return (
    <button
      type="button"
      onClick={() => showToast({
        title: 'Position updated',
        durationMs: 1000,
        action: { label: 'Undo', onClick: () => undefined },
      })}
    >
      Show timed toast
    </button>
  );
};

describe('ToastProvider', () => {
  afterEach(() => vi.useRealTimers());

  it('keeps its live region outside dialog isolation on the authoritative layer', () => {
    render(
      <UiLanguageProvider>
        <ToastProvider>
          <Harness />
        </ToastProvider>
      </UiLanguageProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show toast' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open modal' }));

    const toast = screen.getByRole('status');
    const viewport = toast.closest<HTMLElement>('[data-overlay-root="toast"]');
    expect(viewport).not.toBeNull();
    expect(viewport?.style.zIndex).toBe(String(OVERLAY_Z.toast));
    expect(viewport).not.toHaveAttribute('inert');
    expect(viewport).not.toHaveAttribute('aria-hidden');
    expect(screen.getByRole('dialog', { name: 'Report details' })).toBeVisible();
  });

  it('keeps an actionable toast available while keyboard focus is inside it', () => {
    vi.useFakeTimers();
    render(
      <UiLanguageProvider>
        <ToastProvider>
          <TimedToastHarness />
        </ToastProvider>
      </UiLanguageProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show timed toast' }));
    const toast = screen.getByRole('status');
    const action = screen.getByRole('button', { name: 'Undo' });
    fireEvent.focus(action);
    act(() => vi.advanceTimersByTime(2000));
    expect(toast).toBeVisible();

    fireEvent.blur(action, { relatedTarget: null });
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
