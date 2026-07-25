import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { approvalsApi } from '../../api/approvals';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { ApprovalProposal, ApprovalRule } from '../../types/approvals';
import ApprovalsPage from '../ApprovalsPage';

vi.mock('../../api/approvals', () => ({
  approvalsApi: {
    getRule: vi.fn(),
    updateRule: vi.fn(),
    list: vi.fn(),
    decide: vi.fn(),
  },
}));

const rule: ApprovalRule = {
  owner: 'local_admin',
  action: 'risk_control_bypass',
  enabled: false,
  riskSources: ['risk_veto', 'risk_downgrade'],
  expiresInSeconds: 300,
  version: 0,
  updatedAt: null,
};

function proposal(
  id: string,
  status: ApprovalProposal['status'],
  expiresAt: string,
): ApprovalProposal {
  return {
    id,
    owner: 'local_admin',
    status,
    version: status === 'pending' ? 1 : 2,
    expiresAt,
    consumedAt: status === 'approved' ? '2026-07-25T18:01:00Z' : null,
    context: {
      stockCode: 'AAPL',
      originalSignal: 'buy',
      conservativeSignal: 'hold',
      riskSource: 'risk_veto',
      riskSummary: 'A risk veto would replace the original buy signal.',
    },
  };
}

function renderPage() {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <ApprovalsPage />
    </UiLanguageProvider>,
  );
}

describe('ApprovalsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(approvalsApi.getRule).mockResolvedValue(rule);
    vi.mocked(approvalsApi.list).mockResolvedValue({
      items: [
        proposal('a'.repeat(32), 'pending', new Date(Date.now() + 60_000).toISOString()),
        proposal('b'.repeat(32), 'approved', new Date(Date.now() + 30_000).toISOString()),
        proposal('c'.repeat(32), 'expired', new Date(Date.now() - 1_000).toISOString()),
      ],
      page: 1,
      pageSize: 50,
      total: 3,
    });
  });

  it('renders pending and terminal states with countdown and rule settings', async () => {
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Human approvals' })).toBeInTheDocument();
    expect(screen.getByText(/remaining/)).toBeInTheDocument();
    expect(screen.getAllByText('Approved')).toHaveLength(2);
    expect(screen.getAllByText('Expired')).toHaveLength(2);
    expect(screen.getByRole('switch', { name: 'Enable human approval' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('polls proposals without overwriting an unsaved rule draft', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    renderPage();

    const ruleSwitch = await screen.findByRole('switch', { name: 'Enable human approval' });
    fireEvent.click(ruleSwitch);
    expect(ruleSwitch).toHaveAttribute('aria-checked', 'true');

    const proposalPoll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(proposalPoll).toBeTypeOf('function');
    await act(async () => {
      (proposalPoll as () => void)();
    });

    expect(ruleSwitch).toHaveAttribute('aria-checked', 'true');
    expect(approvalsApi.getRule).toHaveBeenCalledTimes(1);
    expect(approvalsApi.list).toHaveBeenCalledTimes(2);
    intervalSpy.mockRestore();
  });

  it('blocks duplicate decisions and moves a completed proposal to history', async () => {
    let resolveDecision!: (value: ApprovalProposal) => void;
    vi.mocked(approvalsApi.decide).mockReturnValue(new Promise((resolve) => {
      resolveDecision = resolve;
    }));
    renderPage();

    const approve = await screen.findByRole('button', { name: 'Approve original signal' });
    fireEvent.click(approve);
    fireEvent.click(approve);
    expect(approvalsApi.decide).toHaveBeenCalledTimes(1);

    resolveDecision(proposal(
      'a'.repeat(32),
      'approved',
      new Date(Date.now() + 60_000).toISOString(),
    ));
    await waitFor(() => expect(screen.queryByRole(
      'button',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument());
    expect(screen.getAllByText('Approved')).toHaveLength(4);
  });

  it('refreshes after a 409 and recovers rule editing errors', async () => {
    vi.mocked(approvalsApi.decide).mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Conflict',
      response: {
        status: 409,
        data: { error: 'approval_version_conflict', message: 'Conflict' },
      },
    });
    vi.mocked(approvalsApi.updateRule).mockResolvedValueOnce({
      ...rule,
      enabled: true,
      version: 1,
      updatedAt: '2026-07-25T18:00:00Z',
    });
    renderPage();

    const ruleSwitch = await screen.findByRole('switch', { name: 'Enable human approval' });
    fireEvent.click(ruleSwitch);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve original signal' }));
    expect(await screen.findByText('Approval state changed; the page was refreshed.')).toBeInTheDocument();
    expect(approvalsApi.list).toHaveBeenCalledTimes(2);
    expect(approvalsApi.getRule).toHaveBeenCalledTimes(1);
    expect(ruleSwitch).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));
    await waitFor(() => expect(approvalsApi.updateRule).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        expectedVersion: 0,
      }),
    ));
    expect(await screen.findByText('Approval rule saved.')).toBeInTheDocument();
  });

  it('does not hide a rule-save error after successful background polling', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    vi.mocked(approvalsApi.updateRule).mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Rule save failed',
      response: {
        status: 500,
        data: { error: 'rule_save_failed', message: 'Rule save failed' },
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole('switch', { name: 'Enable human approval' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));
    expect(await screen.findByText('Rule save failed')).toBeInTheDocument();

    const proposalPoll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(proposalPoll).toBeTypeOf('function');
    await act(async () => {
      (proposalPoll as () => void)();
    });

    expect(screen.getByText('Rule save failed')).toBeInTheDocument();
    intervalSpy.mockRestore();
  });
});
