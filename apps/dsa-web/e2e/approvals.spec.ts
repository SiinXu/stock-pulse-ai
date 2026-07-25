import { expect, test } from '@playwright/test';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';


test.describe('Human approval real-backend closure', () => {
  test('Home opens approvals, updates the rule, and decides a durable proposal', async ({ page }) => {
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

    const decisionResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/approvals/')
      && response.url().endsWith('/decision')
      && response.status() === 200
    ));
    await page.getByRole('button', {
      name: /批准保留原始信号|Approve original signal/,
    }).click();
    await decisionResponse;
    await expect(page.getByText(/^(已批准|Approved)$/).first()).toBeVisible();
    await expect(page.getByRole('button', {
      name: /批准保留原始信号|Approve original signal/,
    })).toHaveCount(0);
  });
});
