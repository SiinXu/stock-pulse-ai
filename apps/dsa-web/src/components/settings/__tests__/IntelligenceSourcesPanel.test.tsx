// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { INTELLIGENCE_SOURCES_CANCEL } from '../../../hooks/useIntelligenceSourcesQuery';
import { SETTINGS_INTELLIGENCE_TEXT } from '../../../locales/settingsIntelligence';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import { createDeferred } from '../../../test-utils';
import { IntelligenceSourcesPanel } from '../IntelligenceSourcesPanel';

vi.mock('../../../contexts/UiLanguageContext', () => ({
  useUiLanguage: () => ({ language: 'zh', t: (key: string) => key }),
}));

const api = vi.hoisted(() => ({
  listSources: vi.fn(),
  listTemplates: vi.fn(),
  createSource: vi.fn(),
  createSourceFromTemplate: vi.fn(),
  createDefaultSources: vi.fn(),
  testSource: vi.fn(),
  fetchSource: vi.fn(),
  fetchEnabledSources: vi.fn(),
  listItems: vi.fn(),
}));

vi.mock('../../../api/intelligence', () => ({ intelligenceApi: api }));

const emptyList = { items: [], total: 0, page: 1, pageSize: 50 };
const emptyTemplates = { items: [], total: 0 };
const listedSource = {
  id: 3,
  name: '财经RSS',
  sourceType: 'rss',
  url: 'https://feed',
  enabled: true,
  scopeType: 'market',
  market: 'cn',
};
const listedItem = {
  id: 11,
  sourceId: 3,
  sourceName: '财经RSS',
  sourceType: 'rss',
  title: '条目标题甲',
  url: 'https://example.com/item-a',
  scopeType: 'market',
  market: 'cn',
  publishedAt: '2026-09-11',
};
const emptyItems = { items: [], total: 0, page: 1, pageSize: 20 };

function renderPanel() {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <IntelligenceSourcesPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listTemplates.mockResolvedValue(emptyTemplates);
});

describe('IntelligenceSourcesPanel', () => {
  it('shows a loading state before data resolves', () => {
    api.listSources.mockReturnValue(new Promise(() => {}));
    renderPanel();
    expect(screen.getByText('正在加载情报源…')).toBeInTheDocument();
  });

  it('shows an error state with a retry that reloads', async () => {
    api.listSources.mockRejectedValueOnce(new Error('boom'));
    renderPanel();
    await screen.findByText('情报源加载失败');

    api.listSources.mockResolvedValueOnce(emptyList);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await screen.findByText('还没有情报源');
    expect(api.listSources).toHaveBeenCalledTimes(2);
    expect(api.listTemplates).toHaveBeenCalledTimes(2);
  });

  it('fails the whole mount when templates 500 after sources succeed', async () => {
    api.listSources.mockResolvedValue({
      items: [listedSource],
      total: 1,
      page: 1,
      pageSize: 50,
    });
    api.listTemplates.mockRejectedValueOnce(new Error('templates boom'));
    renderPanel();

    await screen.findByText('情报源加载失败');
    expect(screen.queryByText('财经RSS')).not.toBeInTheDocument();
    expect(screen.queryByText('还没有情报源')).not.toBeInTheDocument();
  });

  it('does not flash the error StatePanel when unmounted during mount', async () => {
    const pendingSources = createDeferred<{ items: unknown[]; total: number; page: number; pageSize: number }>();
    const pendingTemplates = createDeferred<{ items: unknown[]; total: number }>();
    api.listSources.mockReturnValueOnce(pendingSources.promise);
    api.listTemplates.mockReturnValueOnce(pendingTemplates.promise);
    const { unmount } = renderPanel();
    expect(screen.getByText('正在加载情报源…')).toBeInTheDocument();
    unmount();

    await act(async () => {
      pendingSources.reject(new Error('late sources'));
      pendingTemplates.reject(new Error('late templates'));
      await pendingSources.promise.catch(() => undefined);
      await pendingTemplates.promise.catch(() => undefined);
    });

    expect(screen.queryByText('情报源加载失败')).not.toBeInTheDocument();
  });

  it('does not flash the error StatePanel when mount GETs settle as silent CancelledError', async () => {
    api.listSources.mockRejectedValue(new CancelledError(INTELLIGENCE_SOURCES_CANCEL));
    renderPanel();
    expect(screen.getByText('正在加载情报源…')).toBeInTheDocument();
    await waitFor(() => expect(api.listSources).toHaveBeenCalled());
    expect(screen.getByText('正在加载情报源…')).toBeInTheDocument();
    expect(screen.queryByText('情报源加载失败')).not.toBeInTheDocument();
  });

  it('offers default sources when empty and creates them', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.createDefaultSources.mockResolvedValueOnce({ items: [], createdCount: 2, total: 2 });
    renderPanel();

    const createButton = await screen.findByRole('button', { name: '创建默认情报源' });
    fireEvent.click(createButton);
    await waitFor(() => expect(api.createDefaultSources).toHaveBeenCalledWith(true));
    expect(api.listItems).not.toHaveBeenCalled();
  });

  it('lists connected sources and fetches one', async () => {
    api.listSources.mockResolvedValue({
      items: [listedSource],
      total: 1,
      page: 1,
      pageSize: 50,
    });
    api.fetchSource.mockResolvedValueOnce({ ok: true, sourceId: 3, fetchedCount: 5, savedCount: 5, sampleItems: [] });
    renderPanel();

    await screen.findByText('财经RSS');
    fireEvent.click(screen.getByRole('button', { name: '抓取' }));
    await waitFor(() => expect(api.fetchSource).toHaveBeenCalledWith(3, false));
    expect(api.listItems).not.toHaveBeenCalled();
  });

  it('mounts the manual source form only after opening the shared dialog', async () => {
    api.listSources.mockResolvedValue(emptyList);
    renderPanel();

    const trigger = await screen.findByRole('button', { name: '新增情报源' });
    expect(screen.queryByRole('textbox', { name: '名称' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '新增情报源' })).not.toBeInTheDocument();

    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: '新增情报源' });
    expect(within(dialog).getByRole('textbox', { name: '名称' })).toBeInTheDocument();
    expect(within(dialog).getByRole('textbox', { name: '来源地址' })).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '新增情报源' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('validates required fields before creating', async () => {
    api.listSources.mockResolvedValue(emptyList);
    renderPanel();
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: '新增情报源' }));
    const dialog = screen.getByRole('dialog', { name: '新增情报源' });
    fireEvent.click(within(dialog).getByRole('button', { name: '添加' }));
    await screen.findByText('请填写名称和来源地址');
    expect(api.createSource).not.toHaveBeenCalled();
  });

  it('closes a successful create and reports a subsequent list refresh failure on the page', async () => {
    api.listSources
      .mockResolvedValueOnce(emptyList)
      .mockRejectedValueOnce(new Error('refresh failed'))
      .mockResolvedValueOnce(emptyList);
    api.createSource.mockResolvedValueOnce({});
    renderPanel();

    await screen.findByText('还没有情报源');
    expect(api.listTemplates).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '新增情报源' }));

    const dialog = screen.getByRole('dialog', { name: '新增情报源' });
    fireEvent.change(within(dialog).getByRole('textbox', { name: '名称' }), {
      target: { value: '财经 RSS' },
    });
    fireEvent.change(within(dialog).getByRole('textbox', { name: '来源地址' }), {
      target: { value: 'https://example.com/feed.xml' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '添加' }));

    await waitFor(() => expect(api.createSource).toHaveBeenCalledWith({
      name: '财经 RSS',
      url: 'https://example.com/feed.xml',
      sourceType: 'rss',
      scopeType: 'market',
      market: 'cn',
      description: undefined,
      enabled: true,
    }));
    expect(await screen.findByText('情报源加载失败')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '新增情报源' })).not.toBeInTheDocument();
    expect(api.listTemplates).toHaveBeenCalledTimes(1);
    expect(api.listSources).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await screen.findByText('还没有情报源');
    expect(api.listTemplates).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: '新增情报源' }));

    const reopenedDialog = screen.getByRole('dialog', { name: '新增情报源' });
    expect(within(reopenedDialog).getByRole('textbox', { name: '名称' })).toHaveValue('');
    expect(within(reopenedDialog).getByRole('textbox', { name: '来源地址' })).toHaveValue('');
  });

  it('does not fetch items on mount', async () => {
    api.listSources.mockResolvedValue(emptyList);
    renderPanel();
    await screen.findByText('还没有情报源');
    expect(api.listItems).not.toHaveBeenCalled();
    expect(screen.queryByText(SETTINGS_INTELLIGENCE_TEXT.zh.noItems)).not.toBeInTheDocument();
  });

  it('loads recent items on click and renders the first title', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.listItems.mockResolvedValueOnce({
      items: [listedItem],
      total: 1,
      page: 1,
      pageSize: 20,
    });
    renderPanel();
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: SETTINGS_INTELLIGENCE_TEXT.zh.loadItems }));
    expect(await screen.findByText('条目标题甲')).toBeInTheDocument();
    expect(api.listItems).toHaveBeenCalledTimes(1);
    expect(api.listItems).toHaveBeenCalledWith({ pageSize: 20 });
    expect(screen.queryByText(SETTINGS_INTELLIGENCE_TEXT.zh.noItems)).not.toBeInTheDocument();
  });

  it('shows noItems for an empty 200 and does not render a list', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.listItems.mockResolvedValueOnce(emptyItems);
    renderPanel();
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: SETTINGS_INTELLIGENCE_TEXT.zh.loadItems }));
    expect(await screen.findByText(SETTINGS_INTELLIGENCE_TEXT.zh.noItems)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(api.listItems).toHaveBeenCalledWith({ pageSize: 20 });
  });

  it('keeps items null on the initial 500 and surfaces the shared alert', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.listItems.mockRejectedValueOnce(new Error('items boom'));
    renderPanel();
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: SETTINGS_INTELLIGENCE_TEXT.zh.loadItems }));
    expect(await screen.findByText('请求未能完成，请稍后重试。')).toBeInTheDocument();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
    expect(screen.queryByText(SETTINGS_INTELLIGENCE_TEXT.zh.noItems)).not.toBeInTheDocument();
    expect(screen.queryByText('条目标题甲')).not.toBeInTheDocument();
  });

  it('keeps last-good titles when a later 500 surfaces the shared alert', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.listItems
      .mockResolvedValueOnce({
        items: [listedItem],
        total: 1,
        page: 1,
        pageSize: 20,
      })
      .mockRejectedValueOnce(new Error('later items boom'));
    renderPanel();
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: SETTINGS_INTELLIGENCE_TEXT.zh.loadItems }));
    expect(await screen.findByText('条目标题甲')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: SETTINGS_INTELLIGENCE_TEXT.zh.loadItems }));
    expect(await screen.findByText('请求未能完成，请稍后重试。')).toBeInTheDocument();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
    expect(screen.getByText('条目标题甲')).toBeInTheDocument();
    expect(screen.queryByText(SETTINGS_INTELLIGENCE_TEXT.zh.noItems)).not.toBeInTheDocument();
  });
});
