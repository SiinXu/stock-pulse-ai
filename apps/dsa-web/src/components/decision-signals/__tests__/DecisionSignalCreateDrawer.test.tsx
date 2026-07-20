import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DecisionSignalCreateDrawer } from '../DecisionSignalCreateDrawer';
import { EMPTY_MANUAL_SIGNAL_DRAFT, type ManualSignalDraft } from '../manualSignalDraft';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { decisionSignalsApi } from '../../../api/decisionSignals';
import type {
  DecisionSignalItem,
  DecisionSignalMutationResponse,
} from '../../../types/decisionSignals';

vi.mock('../../../api/decisionSignals', () => ({
  decisionSignalsApi: { create: vi.fn() },
}));

const createMock = vi.mocked(decisionSignalsApi.create);

// jsdom does not implement scrollIntoView, which Select calls when opening.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function makeItem(overrides: Partial<DecisionSignalItem> = {}): DecisionSignalItem {
  return {
    id: 123,
    stockCode: '600519',
    market: 'cn',
    sourceType: 'manual',
    triggerSource: 'web_manual',
    action: 'buy',
    planQuality: 'minimal',
    status: 'active',
    ...overrides,
  };
}

function Harness({ onCreated = vi.fn() }: { onCreated?: (result: DecisionSignalMutationResponse) => void }) {
  const [open, setOpen] = useState(true);
  const [draft, setDraft] = useState<ManualSignalDraft>(() => ({ ...EMPTY_MANUAL_SIGNAL_DRAFT }));
  return (
    <UiLanguageProvider initialLanguage="en">
      <button type="button" onClick={() => setOpen(true)}>reopen-harness</button>
      <DecisionSignalCreateDrawer
        isOpen={open}
        onClose={() => setOpen(false)}
        draft={draft}
        onDraftChange={setDraft}
        onCreated={onCreated}
      />
    </UiLanguageProvider>
  );
}

function chooseOption(triggerId: string, value: string) {
  const trigger = document.getElementById(triggerId)!;
  fireEvent.click(trigger);
  const listboxId = trigger.getAttribute('aria-controls')!;
  const listbox = document.getElementById(listboxId)!;
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value)!;
  fireEvent.click(option);
}

function fillRequired(stockCode = '600519') {
  fireEvent.change(screen.getByLabelText('Stock code'), { target: { value: stockCode } });
  chooseOption('manual-signal-market', 'cn');
  chooseOption('manual-signal-action', 'buy');
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Create signal' }));
}

describe('DecisionSignalCreateDrawer', () => {
  beforeEach(() => {
    createMock.mockReset();
  });

  it('shows the fixed manual source and trigger', () => {
    render(<Harness />);
    expect(screen.getByText(/Source fixed to Manual · web_manual/).closest('[data-surface-level]'))
      .toHaveAttribute('data-surface-level', 'section');
    expect(screen.getByRole('heading', { name: 'Preview' }).closest('[data-surface-level]'))
      .toHaveAttribute('data-surface-level', 'section');
  });

  it('blocks submit and surfaces required errors when the form is empty', () => {
    render(<Harness />);
    submit();
    expect(createMock).not.toHaveBeenCalled();
    expect(screen.getAllByText('Required.').length).toBeGreaterThanOrEqual(3);
  });

  it('creates a manual signal with fixed source and clears the draft on success', async () => {
    const onCreated = vi.fn();
    createMock.mockResolvedValue({ item: makeItem({ id: 123 }), created: true });
    render(<Harness onCreated={onCreated} />);

    fillRequired();
    submit();

    await waitFor(() => expect(screen.getByText(/Created DecisionSignal #123/)).toBeTruthy());
    expect(createMock).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceType: 'manual',
        triggerSource: 'web_manual',
        stockCode: '600519',
        market: 'cn',
        action: 'buy',
      }),
    );
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ created: true }));
    // Draft was reset after a successful create.
    expect((screen.getByLabelText('Stock code') as HTMLInputElement).value).toBe('');
  });

  it('keeps the draft and reports a dedup hit when created is false', async () => {
    createMock.mockResolvedValue({ item: makeItem({ id: 55 }), created: false });
    render(<Harness />);

    fillRequired();
    submit();

    await waitFor(() => expect(screen.getByText(/identical signal already exists/)).toBeTruthy());
    // Draft is retained so the user can adjust and retry.
    expect((screen.getByLabelText('Stock code') as HTMLInputElement).value).toBe('600519');
  });

  it('keeps the draft when the request fails', async () => {
    createMock.mockRejectedValue(new Error('network'));
    render(<Harness />);

    fillRequired();
    submit();

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect((screen.getByLabelText('Stock code') as HTMLInputElement).value).toBe('600519');
  });

  it('retains the draft across close and reopen', () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText('Stock code'), { target: { value: '600519' } });

    // Close via the drawer's own control; the modal marks outside content
    // aria-hidden, so the reopen affordance is only reachable once closed.
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));
    expect(screen.queryByLabelText('Stock code')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'reopen-harness' }));
    expect((screen.getByLabelText('Stock code') as HTMLInputElement).value).toBe('600519');
  });
});
