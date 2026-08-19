// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Request } from './playwright-test';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';

const APPROVE = /批准保留原始信号|Approve original signal/;
const REJECT = /拒绝并采用保守信号|Reject and use conservative signal/;
const CANCEL = /取消|Cancel/;

function isDecisionRequest(request: Request): boolean {
  if (request.method() !== 'POST') return false;
  let pathname: string;
  try {
    pathname = new URL(request.url()).pathname;
  } catch {
    return false;
  }
  return pathname.startsWith('/api/v1/approvals/') && pathname.endsWith('/decision');
}

test.describe('Human approval real-backend closure', () => {
  test('Home opens approvals, updates the rule, and decides a durable proposal', async ({ page }) => {
    const decisionRequests: Request[] = [];
    page.on('request', (request) => {
      if (isDecisionRequest(request)) {
        decisionRequests.push(request);
      }
    });

    await mockCompletedSetupStatus(page);
    await loginAsE2eAdmin(page);

    await page.getByRole('button', { name: /查看人工审批|Review human approvals/ }).click();
    await expect(page).toHaveURL('/approvals');
    await expect(page.getByRole('heading', { name: /人工审批|Human approvals/ })).toBeVisible();
    await expect(page.getByText('AAPL')).toBeVisible();
    await expect(page.getByText(/A risk veto would replace/)).toBeVisible();

    const ruleSwitch = page.getByRole('switch', { name: /启用人工审批|Enable human approval/ });
    await expect(ruleSwitch).toHaveAttribute('aria-checked', 'false');
    await ruleSwitch.click();
    const saveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/approvals/rules/risk-control-bypass')
      && response.request().method() === 'PUT'
      && response.status() === 200
    ));
    await page.getByRole('button', { name: /保存规则|Save rule/ }).click();
    await saveResponse;
    await expect(ruleSwitch).toHaveAttribute('aria-checked', 'true');

    const approveOnCard = page.getByRole('button', { name: APPROVE });
    const rejectOnCard = page.getByRole('button', { name: REJECT });
    await expect(approveOnCard).toBeEnabled();
    await expect(rejectOnCard).toBeEnabled();

    await approveOnCard.click();
    const approveDialog = page.getByRole('dialog', { name: APPROVE });
    await expect(approveDialog).toBeVisible();
    await expect(approveDialog.getByTestId('approval-decision-confirm-target')).toContainText('AAPL');
    expect(decisionRequests).toHaveLength(0);

    await approveDialog.getByRole('button', { name: CANCEL }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('button', { name: APPROVE })).toBeEnabled();
    await expect(page.getByRole('button', { name: REJECT })).toBeEnabled();
    await expect(page.getByText('AAPL')).toBeVisible();
    expect(decisionRequests).toHaveLength(0);

    await page.getByRole('button', { name: REJECT }).click();
    const rejectDialog = page.getByRole('dialog', { name: REJECT });
    await expect(rejectDialog).toBeVisible();
    await expect(rejectDialog.getByTestId('approval-decision-confirm-target')).toContainText('AAPL');
    expect(decisionRequests).toHaveLength(0);
    await rejectDialog.getByRole('button', { name: CANCEL }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('button', { name: APPROVE })).toBeEnabled();
    expect(decisionRequests).toHaveLength(0);

    await page.getByRole('button', { name: APPROVE }).click();
    const confirmDialog = page.getByRole('dialog', { name: APPROVE });
    await expect(confirmDialog).toBeVisible();
    const decisionResponse = page.waitForResponse((response) => (
      isDecisionRequest(response.request()) && response.status() === 200
    ));
    await confirmDialog.getByRole('button', { name: APPROVE }).click();
    await decisionResponse;
    expect(decisionRequests).toHaveLength(1);

    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText(/^(已批准|Approved)$/).first()).toBeVisible();
    await expect(page.getByRole('button', { name: APPROVE })).toHaveCount(0);
    await expect(page.getByRole('button', { name: REJECT })).toHaveCount(0);
  });
});
