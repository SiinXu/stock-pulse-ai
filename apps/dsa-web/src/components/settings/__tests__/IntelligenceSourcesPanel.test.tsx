// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listTemplates.mockResolvedValue(emptyTemplates);
});

describe('IntelligenceSourcesPanel', () => {
  it('shows a loading state before data resolves', () => {
    api.listSources.mockReturnValue(new Promise(() => {}));
    render(<IntelligenceSourcesPanel />);
    expect(screen.getByText('正在加载情报源…')).toBeInTheDocument();
  });

  it('shows an error state with a retry that reloads', async () => {
    api.listSources.mockRejectedValueOnce(new Error('boom'));
    render(<IntelligenceSourcesPanel />);
    await screen.findByText('情报源加载失败');

    api.listSources.mockResolvedValueOnce(emptyList);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await screen.findByText('还没有情报源');
    expect(api.listSources).toHaveBeenCalledTimes(2);
  });

  it('offers default sources when empty and creates them', async () => {
    api.listSources.mockResolvedValue(emptyList);
    api.createDefaultSources.mockResolvedValueOnce({ items: [], createdCount: 2, total: 2 });
    render(<IntelligenceSourcesPanel />);

    const createButton = await screen.findByRole('button', { name: '创建默认情报源' });
    fireEvent.click(createButton);
    await waitFor(() => expect(api.createDefaultSources).toHaveBeenCalledWith(true));
  });

  it('lists connected sources and fetches one', async () => {
    api.listSources.mockResolvedValue({
      items: [{ id: 3, name: '财经RSS', sourceType: 'rss', url: 'https://feed', enabled: true, scopeType: 'market', market: 'cn' }],
      total: 1,
      page: 1,
      pageSize: 50,
    });
    api.fetchSource.mockResolvedValueOnce({ ok: true, sourceId: 3, fetchedCount: 5, savedCount: 5, sampleItems: [] });
    render(<IntelligenceSourcesPanel />);

    await screen.findByText('财经RSS');
    fireEvent.click(screen.getByRole('button', { name: '抓取' }));
    await waitFor(() => expect(api.fetchSource).toHaveBeenCalledWith(3, false));
  });

  it('validates required fields before creating', async () => {
    api.listSources.mockResolvedValue(emptyList);
    render(<IntelligenceSourcesPanel />);
    await screen.findByText('还没有情报源');

    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    await screen.findByText('请填写名称和来源地址');
    expect(api.createSource).not.toHaveBeenCalled();
  });
});
