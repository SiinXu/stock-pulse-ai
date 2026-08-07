import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
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
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="en">
        <ApprovalsPage />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

function mockHappyLoad(nextRule: ApprovalRule = rule) {
  vi.mocked(approvalsApi.getRule).mockResolvedValue(nextRule);
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
}

describe('ApprovalsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockHappyLoad();
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

  it('shows rule-disabled and risk-override precondition banners on the happy path', async () => {
    renderPage();

    expect(await screen.findByTestId('approvals-precondition-rule-disabled')).toBeInTheDocument();
    expect(screen.getByTestId('approvals-precondition-risk-override')).toBeInTheDocument();
    expect(screen.getAllByText(/AGENT_RISK_OVERRIDE/).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('approvals-precondition-auth-disabled')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve original signal' })).toBeEnabled();
  });

  it('hides the rule-disabled banner when the rule is enabled', async () => {
    mockHappyLoad({ ...rule, enabled: true, version: 1 });
    renderPage();

    expect(await screen.findByTestId('approvals-precondition-risk-override')).toBeInTheDocument();
    expect(screen.queryByTestId('approvals-precondition-rule-disabled')).not.toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Enable human approval' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('explains auth-disabled 403 and blocks decision actions', async () => {
    vi.mocked(approvalsApi.getRule).mockRejectedValue({
      isAxiosError: true,
      message: 'Approval access requires enabled administrator authentication',
      response: {
        status: 403,
        data: {
          error: 'approval_auth_required',
          message: 'Approval access requires enabled administrator authentication',
        },
      },
    });
    vi.mocked(approvalsApi.list).mockRejectedValue({
      isAxiosError: true,
      message: 'Approval access requires enabled administrator authentication',
      response: {
        status: 403,
        data: {
          error: 'approval_auth_required',
          message: 'Approval access requires enabled administrator authentication',
        },
      },
    });
    renderPage();

    expect(await screen.findByTestId('approvals-precondition-auth-disabled')).toBeInTheDocument();
    expect(screen.getByText(/ADMIN_AUTH_ENABLED=true/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Auth & Security settings' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(screen.getAllByText(/cannot be loaded or decided/i).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('approvals-precondition-rule-disabled')).not.toBeInTheDocument();
    expect(screen.queryByText('There are no pending approvals.')).not.toBeInTheDocument();
  });

  it('keeps already-loaded proposals visible but disables decisions after a later 403 poll', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    renderPage();
    expect(await screen.findByRole('button', { name: 'Approve original signal' })).toBeEnabled();

    vi.mocked(approvalsApi.list).mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Approval access requires enabled administrator authentication',
      response: {
        status: 403,
        data: {
          error: 'approval_auth_required',
          message: 'Approval access requires enabled administrator authentication',
        },
      },
    });
    const proposalPoll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(proposalPoll).toBeTypeOf('function');
    await act(async () => {
      (proposalPoll as () => void)();
    });

    expect(await screen.findByTestId('approvals-precondition-auth-disabled')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve original signal' })).toBeDisabled();
    expect(
      screen.getAllByText('A risk veto would replace the original buy signal.').length,
    ).toBeGreaterThan(0);
    intervalSpy.mockRestore();
  });

  it('explains missing session 401 and points to sign-in', async () => {
    vi.mocked(approvalsApi.getRule).mockRejectedValue({
      isAxiosError: true,
      message: 'Administrator authentication required',
      response: {
        status: 401,
        data: {
          error: 'unauthorized',
          message: 'Administrator authentication required',
        },
      },
    });
    vi.mocked(approvalsApi.list).mockRejectedValue({
      isAxiosError: true,
      message: 'Administrator authentication required',
      response: {
        status: 401,
        data: {
          error: 'unauthorized',
          message: 'Administrator authentication required',
        },
      },
    });
    renderPage();

    expect(await screen.findByTestId('approvals-precondition-session-required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go to sign-in' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve original signal' })).not.toBeInTheDocument();
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
    const ruleSaveToast = await screen.findByRole('alert');
    expect(ruleSaveToast.closest('[data-overlay-root="toast"]')).not.toBeNull();
    expect(ruleSaveToast).not.toHaveTextContent('Rule save failed');

    const proposalPoll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(proposalPoll).toBeTypeOf('function');
    await act(async () => {
      (proposalPoll as () => void)();
    });

    expect(ruleSaveToast).toBeInTheDocument();
    intervalSpy.mockRestore();
  });
});
