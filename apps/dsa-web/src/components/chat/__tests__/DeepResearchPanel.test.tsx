import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DeepResearchPanel } from '../DeepResearchPanel';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { agentApi } from '../../../api/agent';

vi.mock('../../../api/agent', () => ({
  agentApi: { research: vi.fn() },
}));

vi.mock('../../../hooks/useStockIndex', () => ({
  useStockIndex: () => ({
    index: [],
    loading: false,
    error: null,
    fallback: false,
    loaded: true,
  }),
}));

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('remark-gfm', () => ({ default: () => undefined }));

const researchMock = vi.mocked(agentApi.research);

function renderPanel(sessionId = 'sess-1', onHistoryChanged = vi.fn(), onRunInBackground = vi.fn()) {
  render(
    <UiLanguageProvider initialLanguage="en">
      <DeepResearchPanel
        sessionId={sessionId}
        onHistoryChanged={onHistoryChanged}
        onRunInBackground={onRunInBackground}
      />
    </UiLanguageProvider>,
  );
}

describe('DeepResearchPanel', () => {
  beforeEach(() => {
    researchMock.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('shows the empty hint before a run', () => {
    renderPanel();
    expect(screen.getByText('Enter a question to start deep research.')).toBeTruthy();
    const stockInput = screen.getByRole('combobox', { name: 'Related stock code' });
    expect(stockInput).toHaveAttribute(
      'aria-haspopup',
      'listbox',
    );
    expect(stockInput).toHaveAttribute(
      'placeholder',
      'Optional, e.g. 600519, HK00700, AAPL',
    );
    expect(screen.getByTestId('deep-research-stock-field')).toHaveClass(
      'w-full',
      'sm:min-w-0',
      'sm:flex-1',
    );
    expect(screen.getByTestId('deep-research-stock-field')).not.toHaveClass('sm:w-64');
    expect(screen.getByTestId('deep-research-stock-field').parentElement).toHaveClass('sm:items-center');
    expect(screen.getByTestId('deep-research-stock-field').parentElement).not.toHaveClass('sm:items-end');
    expect(screen.queryByText('Optional, e.g. 600519, HK00700, AAPL')).not.toBeInTheDocument();
    expect(stockInput.parentElement?.parentElement).toHaveClass('[&>div>p]:sr-only');

    fireEvent.mouseEnter(screen.getByTestId('deep-research-stock-help'));
    expect(screen.getByRole('tooltip')).toHaveTextContent(/Japan 7203\.T/);
    expect(screen.getByRole('tooltip')).toHaveTextContent(/If no suggestion appears/);
  });

  it('keeps the empty hint lightweight and the research configuration at the bottom', () => {
    renderPanel();

    const hint = screen.getByText('Enter a question to start deep research.');
    const section = hint.closest('section');
    const form = section?.querySelector('form');

    expect(hint).toHaveClass('text-muted-text');
    expect(hint).not.toHaveClass('font-semibold');
    expect(section).toHaveClass('flex', 'min-h-full', 'flex-col');
    expect(form).toHaveClass('mt-auto');
    expect(section?.lastElementChild).toBe(form);
  });

  it('runs research and renders findings with sub-question references', async () => {
    researchMock.mockResolvedValue({ success: true, content: 'Moutai has a strong moat.', sources: ['What is the moat?', 'What are the risks?'], token_usage: 100 });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'Moutai moat?' } });
    fireEvent.change(screen.getByLabelText('Related stock code'), { target: { value: '600519' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));

    await waitFor(() => expect(screen.getByText('Moutai has a strong moat.')).toBeTruthy());
    expect(researchMock).toHaveBeenCalledWith(
      {
        question: 'Moutai moat?',
        stockCode: '600519',
        sessionId: 'sess-1',
        turnId: expect.any(String),
      },
    );
    expect(screen.getByText('Sub-questions and references')).toBeTruthy();
    expect(screen.getByText('What is the moat?')).toBeTruthy();
  });

  it('preserves Enter submission for a manually entered stock code', async () => {
    researchMock.mockResolvedValue({
      success: true,
      content: 'Submitted with the keyboard.',
      sources: [],
      token_usage: 20,
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Research question'), {
      target: { value: 'Keyboard submission?' },
    });
    const stockInput = screen.getByLabelText('Related stock code');
    fireEvent.change(stockInput, { target: { value: 'AAPL' } });
    fireEvent.keyDown(stockInput, { key: 'Enter' });

    await waitFor(() => {
      expect(researchMock).toHaveBeenCalledWith(
        {
          question: 'Keyboard submission?',
          stockCode: 'AAPL',
          sessionId: 'sess-1',
          turnId: expect.any(String),
        },
      );
    });
  });

  it('refreshes conversation history after research completes', async () => {
    const onHistoryChanged = vi.fn();
    researchMock.mockResolvedValue({
      success: true,
      content: 'Saved findings.',
      sources: [],
      token_usage: 20,
    });
    renderPanel('sess-history', onHistoryChanged);

    fireEvent.change(screen.getByLabelText('Research question'), {
      target: { value: 'Persist this research' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));

    await waitFor(() => expect(onHistoryChanged).toHaveBeenCalledTimes(1));
  });

  it('moves an active run to the background without cancelling the request', async () => {
    const onRunInBackground = vi.fn();
    researchMock.mockReturnValue(new Promise(() => undefined));
    renderPanel('sess-background', vi.fn(), onRunInBackground);

    fireEvent.change(screen.getByLabelText('Research question'), {
      target: { value: 'Keep running' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Run in background' }));

    expect(onRunInBackground).toHaveBeenCalledTimes(1);
  });

  it('surfaces an error when the research response is unsuccessful', async () => {
    researchMock.mockResolvedValue({ success: false, content: '', sources: [], token_usage: 0, error: 'agent_research_failed' });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'Q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));

    await waitFor(() => expect(screen.getByText('Research failed')).toBeTruthy());
    expect(screen.getByText('Deep research could not finish. Try again later.')).toBeTruthy();
    expect(screen.queryByText('agent_research_failed')).not.toBeInTheDocument();
    expect(screen.getByText('Research failed').closest('[data-overlay-root="toast"]')).toBeTruthy();
  });

  it('rejects a successful research response with an empty conclusion', async () => {
    researchMock.mockResolvedValue({
      success: true,
      content: '   ',
      sources: ['Sub-question 1: Q'],
      token_usage: 42,
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'Q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));

    await waitFor(() => expect(screen.getByText('Research failed')).toBeTruthy());
    expect(screen.getByText('Research failed').closest('[data-overlay-root="toast"]')).toBeTruthy();
    expect(screen.queryByText('Research result')).not.toBeInTheDocument();
    expect(screen.queryByText('Sub-question 1: Q')).not.toBeInTheDocument();
  });

  it('restores a persisted completed run for the session on mount', () => {
    const stored = {
      question: 'Prior question',
      stockCode: '',
      status: 'done',
      content: 'Restored findings.',
      sources: ['Prior sub-question'],
    };
    window.sessionStorage.setItem('dsa_research_run:sess-restore', JSON.stringify(stored));

    renderPanel('sess-restore');

    expect(screen.getByText('Restored findings.')).toBeTruthy();
    expect(screen.getByText('Prior sub-question')).toBeTruthy();
    expect((screen.getByLabelText('Research question') as HTMLTextAreaElement).value).toBe('Prior question');
  });

  it('converts a persisted blank completed run into a visible failure', () => {
    window.sessionStorage.setItem('dsa_research_run:sess-blank', JSON.stringify({
      question: 'Prior blank question',
      stockCode: 'NVTS',
      status: 'done',
      content: '   ',
      sources: ['Sub-question 1: Prior blank question'],
    }));

    renderPanel('sess-blank');

    expect(screen.getByText('Research failed')).toBeTruthy();
    expect(screen.getByText('Research failed').closest('[data-overlay-root="toast"]')).toBeTruthy();
    expect(screen.queryByText('Research result')).not.toBeInTheDocument();
    expect(screen.queryByText('Sub-question 1: Prior blank question')).not.toBeInTheDocument();
  });

  it('does not restore a stale running state (coerces it to re-runnable)', () => {
    const stored: { question: string; stockCode: string; status: string } = { question: 'Interrupted', stockCode: '', status: 'running' };
    window.sessionStorage.setItem('dsa_research_run:sess-run', JSON.stringify(stored));
    renderPanel('sess-run');
    // A running run cannot resume after refresh; the Start button is available again.
    expect(screen.getByRole('button', { name: 'Start research' })).toBeTruthy();
  });

  it('migrates a legacy local run into session storage', () => {
    window.localStorage.setItem('dsa_research_run:sess-legacy', JSON.stringify({
      question: 'Legacy question',
      stockCode: 'AAPL',
      status: 'done',
      content: 'Migrated findings.',
    }));

    renderPanel('sess-legacy');

    expect(screen.getByText('Migrated findings.')).toBeTruthy();
    expect(window.localStorage.getItem('dsa_research_run:sess-legacy')).toBeNull();
    expect(window.sessionStorage.getItem('dsa_research_run:sess-legacy')).toContain('Migrated findings.');
  });
});
