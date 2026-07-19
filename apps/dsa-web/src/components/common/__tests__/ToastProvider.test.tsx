import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ToastProvider } from '../ToastProvider';
import { useToast } from '../toastContext';

const Harness = ({ onAction = () => undefined }: { onAction?: () => void }) => {
  const { clearToasts, showToast } = useToast();
  return (
    <>
      <button
        type="button"
        onClick={() => showToast({
          title: 'Report ready',
          message: 'AAPL analysis completed',
          tone: 'success',
          durationMs: 0,
          action: { label: 'Open', onClick: onAction },
        })}
      >
        Show success
      </button>
      <button type="button" onClick={() => showToast({ title: 'Failed', tone: 'danger', durationMs: 1000 })}>
        Show error
      </button>
      <button type="button" onClick={clearToasts}>Clear</button>
    </>
  );
};

function renderHarness(maxVisible?: number, onAction?: () => void) {
  return render(
    <UiLanguageProvider>
      <ToastProvider maxVisible={maxVisible}>
        <Harness onAction={onAction} />
      </ToastProvider>
    </UiLanguageProvider>,
  );
}

describe('ToastProvider', () => {
  it('renders actionable status feedback and dismisses after the action', () => {
    const onAction = vi.fn();
    renderHarness(undefined, onAction);

    fireEvent.click(screen.getByRole('button', { name: 'Show success' }));
    const toast = screen.getByRole('status');
    expect(toast).toHaveTextContent('Report ready');
    expect(toast).toHaveAttribute('data-toast-tone', 'success');
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('uses alert semantics for failures and auto-dismisses them', () => {
    vi.useFakeTimers();
    renderHarness();
    fireEvent.click(screen.getByRole('button', { name: 'Show error' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it('caps the visible queue and supports clearing it', () => {
    renderHarness(2);
    fireEvent.click(screen.getByRole('button', { name: 'Show success' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show success' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show success' }));
    expect(screen.getAllByRole('status')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
