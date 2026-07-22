import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DeepResearchPanel } from '../DeepResearchPanel';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { agentApi } from '../../../api/agent';

vi.mock('../../../api/agent', () => ({
  agentApi: { research: vi.fn() },
}));

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('remark-gfm', () => ({ default: () => undefined }));

const researchMock = vi.mocked(agentApi.research);

function renderPanel(sessionId = 'sess-1') {
  render(
    <UiLanguageProvider initialLanguage="en">
      <DeepResearchPanel sessionId={sessionId} />
    </UiLanguageProvider>,
  );
}

describe('DeepResearchPanel', () => {
  beforeEach(() => {
    researchMock.mockReset();
    window.localStorage.clear();
  });

  it('shows the empty hint before a run', () => {
    renderPanel();
    expect(screen.getByText('Enter a question to start deep research.')).toBeTruthy();
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
      { question: 'Moutai moat?', stockCode: '600519' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByText('Sub-questions and references')).toBeTruthy();
    expect(screen.getByText('What is the moat?')).toBeTruthy();
  });

  it('surfaces an error when the research response is unsuccessful', async () => {
    researchMock.mockResolvedValue({ success: false, content: '', sources: [], token_usage: 0, error: 'timed out after 180s' });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'Q' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }));

    await waitFor(() => expect(screen.getByText('timed out after 180s')).toBeTruthy());
  });

  it('restores a persisted completed run for the session on mount', () => {
    const stored = {
      question: 'Prior question',
      stockCode: '',
      status: 'done',
      content: 'Restored findings.',
      sources: ['Prior sub-question'],
    };
    window.localStorage.setItem('dsa_research_run:sess-restore', JSON.stringify(stored));

    renderPanel('sess-restore');

    expect(screen.getByText('Restored findings.')).toBeTruthy();
    expect(screen.getByText('Prior sub-question')).toBeTruthy();
    expect((screen.getByLabelText('Research question') as HTMLTextAreaElement).value).toBe('Prior question');
  });

  it('does not restore a stale running state (coerces it to re-runnable)', () => {
    const stored: { question: string; stockCode: string; status: string } = { question: 'Interrupted', stockCode: '', status: 'running' };
    window.localStorage.setItem('dsa_research_run:sess-run', JSON.stringify(stored));
    renderPanel('sess-run');
    // A running run cannot resume after refresh; the Start button is available again.
    expect(screen.getByRole('button', { name: 'Start research' })).toBeTruthy();
  });
});
