import { afterEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../../api';
import { alertsApi } from '../../api/alerts';
import { agentApi } from '../../api/agent';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { historyApi } from '../../api/history';
import { intelligenceApi } from '../../api/intelligence';
import { systemConfigApi } from '../../api/systemConfig';
import { installPlaygroundApiMock } from '../mockApi';

let activeSandbox: ReturnType<typeof installPlaygroundApiMock> | null = null;

function install(...args: Parameters<typeof installPlaygroundApiMock>) {
  activeSandbox = installPlaygroundApiMock(...args);
  return activeSandbox;
}

afterEach(() => {
  activeSandbox?.restore();
  activeSandbox = null;
});

describe('playground API sandbox', () => {
  it('returns populated wire-compatible fixtures through the real API clients', async () => {
    install('ready', { delayResponse: 0 });

    const history = await historyApi.getList();
    const news = await historyApi.getNews(101);
    const models = await systemConfigApi.getLlmAvailableModels();
    const research = await agentApi.research({ question: 'Fixture question' });
    const intelligence = await intelligenceApi.listSources();
    const outcomeRun = await decisionSignalsApi.runOutcomes({ status: 'active', force: false, limit: 100 });
    const notifications = await alertsApi.listNotifications();

    expect(history.items[0]).toMatchObject({ stockCode: '600519', stockName: 'Kweichow Moutai' });
    expect(news.items[0]).toMatchObject({ title: 'Earnings visibility improves' });
    expect(models.models[0]).toMatchObject({ modelRef: expect.any(String), connectionName: 'Fixture connection' });
    expect(research).toMatchObject({ success: true, token_usage: 128 });
    expect(intelligence.items[0]).toMatchObject({ name: 'Market fixture feed', sourceType: 'rss' });
    expect(outcomeRun).toMatchObject({ evaluated: 25, created: 15, engineVersion: 'playground-v1' });
    expect(notifications.items[0]).toMatchObject({
      channel: 'email',
      success: true,
      diagnostics: 'fixture-notification-701',
    });
  });

  it('returns deterministic empty fixtures', async () => {
    install('empty', { delayResponse: 0 });

    await expect(historyApi.getList()).resolves.toMatchObject({ total: 0, items: [] });
    await expect(systemConfigApi.getLlmAvailableModels()).resolves.toEqual({ models: [] });
    await expect(intelligenceApi.listSources()).resolves.toMatchObject({ total: 0, items: [] });
  });

  it('returns deterministic service errors', async () => {
    install('error', { delayResponse: 0 });

    await expect(historyApi.getList()).rejects.toMatchObject({
      response: { status: 503, data: { error: 'playground_fixture_error' } },
    });
  });

  it('uses the documented delay for the slow profile', () => {
    const sandbox = install('slow');
    expect((sandbox.mock as unknown as { delayResponse: number }).delayResponse).toBe(1200);
  });

  it('keeps config, watchlist, and alert writes in memory for subsequent reads', async () => {
    install('ready', { delayResponse: 0 });

    const before = await systemConfigApi.getConfig();
    await systemConfigApi.update({
      configVersion: before.configVersion,
      maskToken: before.maskToken,
      items: [{ key: 'REPORT_LANGUAGE', value: 'en' }],
    });
    expect((await systemConfigApi.getConfig()).items.find((item) => item.key === 'REPORT_LANGUAGE')?.value).toBe('en');

    await systemConfigApi.addToWatchlist('MSFT');
    expect(await systemConfigApi.getWatchlist()).toContain('MSFT');
    await systemConfigApi.removeFromWatchlist('MSFT');
    expect(await systemConfigApi.getWatchlist()).not.toContain('MSFT');

    const created = await alertsApi.createRule({
      name: 'Fixture test rule',
      target: 'AAPL',
      alertType: 'price_cross',
      parameters: { direction: 'above', price: 250 },
      severity: 'warning',
      enabled: true,
    });
    expect((await alertsApi.listRules()).items.some((item) => item.id === created.id)).toBe(true);
    await alertsApi.disableRule(created.id);
    expect((await alertsApi.listRules()).items.find((item) => item.id === created.id)?.enabled).toBe(false);
    await alertsApi.deleteRule(created.id);
    expect((await alertsApi.listRules()).items.some((item) => item.id === created.id)).toBe(false);

    const createdSignal = await decisionSignalsApi.create({
      stockCode: 'MSFT',
      stockName: 'Microsoft',
      market: 'us',
      sourceType: 'manual',
      triggerSource: 'web_manual',
      action: 'watch',
    });
    expect(createdSignal).toMatchObject({ created: true, item: { stockCode: 'MSFT', sourceType: 'manual' } });
    expect((await decisionSignalsApi.list()).items.some((item) => item.id === createdSignal.item.id)).toBe(true);

    const createdSource = await intelligenceApi.createSource({
      name: 'Second fixture feed',
      url: 'https://example.invalid/second.xml',
      sourceType: 'rss',
      scopeType: 'market',
      market: 'us',
    });
    expect((await intelligenceApi.listSources()).items.some((item) => item.id === createdSource.id)).toBe(true);
  });

  it('starts empty-profile writes from empty memory and makes them readable', async () => {
    install('empty', { delayResponse: 0 });

    expect((await intelligenceApi.listSources()).items).toEqual([]);
    await intelligenceApi.createSource({
      name: 'First empty-profile feed',
      url: 'https://example.invalid/empty-profile.xml',
    });
    expect((await intelligenceApi.listSources()).items).toHaveLength(1);
  });

  it('blocks unregistered requests without passthrough', async () => {
    install('ready', { delayResponse: 0 });

    await expect(apiClient.get('/api/v1/playground/unregistered')).rejects.toMatchObject({
      response: {
        status: 501,
        data: { error: 'playground_mock_not_registered' },
      },
    });
  });

  it('restores the original adapter and ejects request-log interceptors', async () => {
    const originalAdapter = apiClient.defaults.adapter;
    const firstLog = vi.fn();
    const secondLog = vi.fn();
    const first = install('ready', { delayResponse: 0, onRequestLog: firstLog });

    await historyApi.getList();
    expect(firstLog).toHaveBeenCalledTimes(1);
    first.restore();
    activeSandbox = null;
    expect(apiClient.defaults.adapter).toBe(originalAdapter);

    install('ready', { delayResponse: 0, onRequestLog: secondLog });
    await historyApi.getList();
    expect(firstLog).toHaveBeenCalledTimes(1);
    expect(secondLog).toHaveBeenCalledTimes(1);
  });
});
