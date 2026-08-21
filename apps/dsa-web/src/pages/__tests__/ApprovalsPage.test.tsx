import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { MemoryRouter } from 'react-router-dom';
import { approvalsApi } from '../../api/approvals';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { createDeferred } from '../../test-utils';
import type { ApprovalProposal, ApprovalProposalPage, ApprovalRule } from '../../types/approvals';
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
  status: ApprovalProposal['status'] | string,
  expiresAt: string,
  context: Partial<ApprovalProposal['context']> = {},
): ApprovalProposal {
  return {
    id,
    owner: 'local_admin',
    status: status as ApprovalProposal['status'],
    version: status === 'pending' ? 1 : 2,
    expiresAt,
    consumedAt: status === 'approved' ? '2026-07-25T18:01:00Z' : null,
    context: {
      stockCode: 'AAPL',
      originalSignal: 'buy',
      conservativeSignal: 'hold',
      riskSource: 'risk_veto',
      riskSummary: 'A risk veto would replace the original buy signal.',
      ...context,
    },
  };
}

async function openDecisionConfirm(name: 'Approve original signal' | 'Reject and use conservative signal') {
  const trigger = await screen.findByRole('button', { name });
  trigger.focus();
  fireEvent.click(trigger);
  return screen.findByRole('dialog', { name });
}

function expectApprovalsConfirmLockHeld() {
  const page = screen.getByTestId('approvals-page');
  expect(page.closest('[inert]')).not.toBeNull();
  expect(page.closest('[aria-hidden="true"]')).not.toBeNull();
  expect(document.body.style.overflow).toBe('hidden');
}

async function waitForApprovalsConfirmLockHeld() {
  await waitFor(() => {
    expectApprovalsConfirmLockHeld();
  });
}

async function waitForApprovalsConfirmLockReleased() {
  await waitFor(() => {
    const page = screen.getByTestId('approvals-page');
    expect(page.closest('[inert]')).toBeNull();
    expect(page.closest('[aria-hidden="true"]')).toBeNull();
    expect(document.body.style.overflow).not.toBe('hidden');
  });
}

function happyListPage(): ApprovalProposalPage {
  return {
    items: [
      proposal('a'.repeat(32), 'pending', new Date(Date.now() + 60_000).toISOString()),
      proposal('b'.repeat(32), 'approved', new Date(Date.now() + 30_000).toISOString()),
      proposal('c'.repeat(32), 'expired', new Date(Date.now() - 1_000).toISOString()),
    ],
    page: 1,
    pageSize: 50,
    total: 3,
  };
}

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function wrapWithQueryClient(ui: ReactElement): ReactElement {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function renderPage() {
  return render(
    wrapWithQueryClient(
      <MemoryRouter>
        <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <UiLanguageProvider initialLanguage="en">
          <ApprovalsPage />
        </UiLanguageProvider>
      </RouteFocusRegistrationContext.Provider>
      </MemoryRouter>,
    ),
  );
}

function mockHappyLoad(nextRule: ApprovalRule = rule) {
  vi.mocked(approvalsApi.getRule).mockResolvedValue(nextRule);
  vi.mocked(approvalsApi.list).mockResolvedValue(happyListPage());
  vi.mocked(approvalsApi.decide).mockImplementation(async (id, decision) => (
    proposal(
      id,
      decision === 'cancelled' ? 'cancelled' : decision,
      new Date(Date.now() + 60_000).toISOString(),
    )
  ));
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
    expect(screen.getByText(/mandatory Risk Manager final-action decision always runs first/)).toBeInTheDocument();
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

  it('closes an open confirmation after a later 403 poll without submitting', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    renderPage();
    await openDecisionConfirm('Approve original signal');

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
    expect(screen.queryByRole('dialog', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(approvalsApi.decide).not.toHaveBeenCalled();
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

    const dialog = await openDecisionConfirm('Approve original signal');
    const confirm = within(dialog).getByRole('button', { name: 'Approve original signal' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(approvalsApi.decide).toHaveBeenCalledTimes(1);

    resolveDecision(proposal(
      'a'.repeat(32),
      'approved',
      new Date(Date.now() + 60_000).toISOString(),
    ));
    await waitFor(() => expect(screen.queryByRole(
      'dialog',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument());
    expect(screen.queryByRole(
      'button',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument();
    expect(screen.getAllByText('Approved')).toHaveLength(4);
  });

  it('refreshes after a 409 and recovers rule editing errors', async () => {
    const decision = createDeferred<ApprovalProposal>();
    const recoveryList = createDeferred<ApprovalProposalPage>();
    vi.mocked(approvalsApi.updateRule).mockResolvedValueOnce({
      ...rule,
      enabled: true,
      version: 1,
      updatedAt: '2026-07-25T18:00:00Z',
    });
    renderPage();

    const ruleSwitch = await screen.findByRole('switch', { name: 'Enable human approval' });
    fireEvent.click(ruleSwitch);
    const dialog = await openDecisionConfirm('Approve original signal');
    await waitForApprovalsConfirmLockHeld();

    vi.mocked(approvalsApi.decide).mockReturnValue(decision.promise);
    void decision.promise.catch(() => undefined);
    vi.mocked(approvalsApi.list).mockImplementation(() => recoveryList.promise);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve original signal' }));
    const busyConfirm = await within(dialog).findByRole('button', { name: 'Processing…' });
    expect(busyConfirm).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expectApprovalsConfirmLockHeld();
    // Isolation hides the page from the accessibility tree; queryByRole is not a lock-release signal.
    expect(screen.queryByRole('button', { name: 'Save rule' })).not.toBeInTheDocument();
    fireEvent.click(busyConfirm);
    expect(approvalsApi.decide).toHaveBeenCalledTimes(1);

    await act(async () => {
      decision.reject({
        isAxiosError: true,
        message: 'Conflict',
        response: {
          status: 409,
          data: { error: 'approval_version_conflict', message: 'Conflict' },
        },
      });
    });
    await waitFor(() => expect(approvalsApi.list).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('dialog', { name: 'Approve original signal' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Processing…' })).toBeDisabled();
    expectApprovalsConfirmLockHeld();
    expect(screen.queryByRole('button', { name: 'Save rule' })).not.toBeInTheDocument();
    expect(screen.queryByText('Approval state changed; the page was refreshed.')).not.toBeInTheDocument();

    await act(async () => {
      recoveryList.resolve(happyListPage());
    });
    expect(await screen.findByText('Approval state changed; the page was refreshed.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(approvalsApi.list).toHaveBeenCalledTimes(2);
    expect(approvalsApi.getRule).toHaveBeenCalledTimes(1);
    expect(ruleSwitch).toHaveAttribute('aria-checked', 'true');
    await waitForApprovalsConfirmLockReleased();
    expect(screen.getByRole('button', { name: 'Approve original signal' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save rule' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));
    await waitFor(() => expect(approvalsApi.updateRule).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        expectedVersion: 0,
      }),
    ));
    expect(await screen.findByText('Approval rule saved.')).toBeInTheDocument();
  });

  it('reloads after a rule-save 409 through the shared recovery contract', async () => {
    vi.mocked(approvalsApi.updateRule).mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Conflict',
      response: {
        status: 409,
        data: { error: 'approval_version_conflict', message: 'Conflict' },
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole('switch', { name: 'Enable human approval' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));

    expect(await screen.findByText('Approval state changed; the page was refreshed.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save rule' })).toBeEnabled();
    expect(approvalsApi.getRule).toHaveBeenCalledTimes(2);
    expect(approvalsApi.list).toHaveBeenCalledTimes(2);
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

  it('requires a second confirmation that names the approve action and target', async () => {
    renderPage();

    const dialog = await openDecisionConfirm('Approve original signal');
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    const target = within(dialog).getByTestId('approval-decision-confirm-target');
    expect(target).toHaveTextContent('AAPL');
    expect(target).toHaveTextContent('Original signal');
    expect(target).toHaveTextContent('Buy');
    expect(target).toHaveTextContent('Conservative signal');
    expect(target).toHaveTextContent('Hold');
    expect(target).toHaveTextContent('Risk veto');
    expect(target).not.toHaveTextContent('buy');
    expect(target).not.toHaveTextContent('risk_veto');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve original signal' }));
    await waitFor(() => expect(approvalsApi.decide).toHaveBeenCalledWith(
      'a'.repeat(32),
      'approved',
      1,
    ));
  });

  it('requires a danger confirmation that names the reject action and target', async () => {
    renderPage();

    const dialog = await openDecisionConfirm('Reject and use conservative signal');
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    expect(within(dialog).getByTestId('approval-decision-confirm-target')).toHaveTextContent('AAPL');
    expect(within(dialog).getByRole('button', { name: 'Reject and use conservative signal' })).toHaveAttribute(
      'data-variant',
      'danger',
    );

    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject and use conservative signal' }));
    await waitFor(() => expect(approvalsApi.decide).toHaveBeenCalledWith(
      'a'.repeat(32),
      'rejected',
      1,
    ));
  });

  it('cancels from the dialog without submitting a decision', async () => {
    renderPage();

    const dialog = await openDecisionConfirm('Approve original signal');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(approvalsApi.decide).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve original signal' })).toBeEnabled();
  });

  it('treats Escape and backdrop click as a default-safe cancel and restores focus', async () => {
    renderPage();

    const trigger = await screen.findByRole('button', { name: 'Approve original signal' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: 'Approve original signal' });

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole(
      'dialog',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    const reopened = await screen.findByRole('dialog', { name: 'Approve original signal' });
    fireEvent.click(reopened.closest('[data-overlay-root="confirm"]') as HTMLElement);
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole(
      'dialog',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it('keeps the confirmation open after a server failure and allows retry', async () => {
    vi.mocked(approvalsApi.decide)
      .mockRejectedValueOnce({
        isAxiosError: true,
        message: 'decision_failed',
        response: {
          status: 500,
          data: { error: 'decision_failed', message: 'decision_failed' },
        },
      })
      .mockResolvedValueOnce(proposal(
        'a'.repeat(32),
        'approved',
        new Date(Date.now() + 60_000).toISOString(),
      ));
    renderPage();

    const dialog = await openDecisionConfirm('Approve original signal');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve original signal' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).not.toHaveTextContent('decision_failed');
    expect(screen.getByRole('dialog', { name: 'Approve original signal' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Approve original signal' })).toBeEnabled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve original signal' }));
    await waitFor(() => expect(approvalsApi.decide).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole(
      'dialog',
      { name: 'Approve original signal' },
    )).not.toBeInTheDocument());
  });

  it('closes confirmation when polling reveals a stale approval', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    renderPage();
    await openDecisionConfirm('Approve original signal');

    vi.mocked(approvalsApi.list).mockResolvedValueOnce({
      items: [
        proposal('a'.repeat(32), 'expired', new Date(Date.now() - 1_000).toISOString()),
        proposal('b'.repeat(32), 'approved', new Date(Date.now() + 30_000).toISOString()),
        proposal('c'.repeat(32), 'expired', new Date(Date.now() - 1_000).toISOString()),
      ],
      page: 1,
      pageSize: 50,
      total: 3,
    });
    const proposalPoll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(proposalPoll).toBeTypeOf('function');
    await act(async () => {
      (proposalPoll as () => void)();
    });

    expect(await screen.findByText('Approval state changed; the page was refreshed.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    intervalSpy.mockRestore();
  });

  it('refreshes proposals when local expiry closes the confirmation', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    const start = Date.now();
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(start);
    vi.mocked(approvalsApi.list).mockResolvedValue({
      items: [
        proposal('a'.repeat(32), 'pending', new Date(start + 2_000).toISOString()),
        proposal('b'.repeat(32), 'approved', new Date(start + 30_000).toISOString()),
        proposal('c'.repeat(32), 'expired', new Date(start - 1_000).toISOString()),
      ],
      page: 1,
      pageSize: 50,
      total: 3,
    });
    renderPage();
    await openDecisionConfirm('Approve original signal');
    expect(approvalsApi.list).toHaveBeenCalledTimes(1);

    nowSpy.mockReturnValue(start + 3_000);
    vi.mocked(approvalsApi.list).mockResolvedValue({
      items: [
        proposal('a'.repeat(32), 'expired', new Date(start - 1_000).toISOString()),
        proposal('b'.repeat(32), 'approved', new Date(start + 30_000).toISOString()),
        proposal('c'.repeat(32), 'expired', new Date(start - 1_000).toISOString()),
      ],
      page: 1,
      pageSize: 50,
      total: 3,
    });
    const countdownTick = intervalSpy.mock.calls.find(([, delay]) => delay === 1_000)?.[0];
    expect(countdownTick).toBeTypeOf('function');
    await act(async () => {
      (countdownTick as () => void)();
    });

    expect(await screen.findByText('Approval state changed; the page was refreshed.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Approve original signal' })).not.toBeInTheDocument();
    expect(approvalsApi.list).toHaveBeenCalledTimes(2);
    expect(approvalsApi.decide).not.toHaveBeenCalled();
    expect(within(screen.getByTestId(`approval-${'a'.repeat(32)}`)).getAllByText('Expired').length).toBeGreaterThan(0);
    nowSpy.mockRestore();
    intervalSpy.mockRestore();
  });

  it('maps known approval codes and keeps unknown codes visible', async () => {
    vi.mocked(approvalsApi.list).mockResolvedValue({
      items: [
        proposal('a'.repeat(32), 'pending', new Date(Date.now() + 60_000).toISOString()),
        proposal('e'.repeat(32), 'pending', new Date(Date.now() + 60_000).toISOString(), {
          stockCode: 'MSFT',
          originalSignal: 'moonshot' as ApprovalProposal['context']['originalSignal'],
          conservativeSignal: 'hold',
          riskSource: 'custom_risk' as ApprovalProposal['context']['riskSource'],
        }),
        proposal('d'.repeat(32), 'mystery_status', new Date(Date.now() + 30_000).toISOString(), {
          originalSignal: 'moonshot' as ApprovalProposal['context']['originalSignal'],
          conservativeSignal: 'hold',
          riskSource: 'custom_risk' as ApprovalProposal['context']['riskSource'],
        }),
      ],
      page: 1,
      pageSize: 50,
      total: 3,
    });
    renderPage();

    const pendingCard = await screen.findByTestId(`approval-${'a'.repeat(32)}`);
    expect(within(pendingCard).getByText('Buy')).toBeInTheDocument();
    expect(within(pendingCard).getByText('Hold')).toBeInTheDocument();
    expect(within(pendingCard).getByText('Risk veto')).toBeInTheDocument();
    expect(within(pendingCard).queryByText('buy')).not.toBeInTheDocument();
    expect(within(pendingCard).queryByText('risk_veto')).not.toBeInTheDocument();

    const unknownCard = screen.getByTestId(`approval-${'d'.repeat(32)}`);
    expect(within(unknownCard).getAllByText('mystery_status').length).toBeGreaterThan(0);
    expect(within(unknownCard).getByText('moonshot')).toBeInTheDocument();
    expect(within(unknownCard).getByText('custom_risk')).toBeInTheDocument();

    fireEvent.click(within(screen.getByTestId(`approval-${'e'.repeat(32)}`)).getByRole(
      'button',
      { name: 'Approve original signal' },
    ));
    const dialog = await screen.findByRole('dialog', { name: 'Approve original signal' });
    const target = within(dialog).getByTestId('approval-decision-confirm-target');
    expect(target).toHaveTextContent('MSFT');
    expect(target).toHaveTextContent('moonshot');
    expect(target).toHaveTextContent('custom_risk');
    expect(target).toHaveTextContent('Hold');
  });
});
