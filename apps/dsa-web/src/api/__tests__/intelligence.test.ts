// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { intelligenceApi } from '../intelligence';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('../index', () => ({
  default: { get, post },
}));

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe('intelligenceApi', () => {
  it('lists sources with query params and camelCases the response', async () => {
    get.mockResolvedValueOnce({
      data: {
        items: [
          { id: 1, name: 'A', source_type: 'rss', url: 'https://a', enabled: true, scope_type: 'market', market: 'cn', last_status: 'ok', last_fetched_at: '2026-07-19' },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      },
    });

    const result = await intelligenceApi.listSources({ enabled: true, page: 1, pageSize: 50 });

    expect(get).toHaveBeenCalledWith('/api/v1/intelligence/sources', {
      params: { enabled: true, source_type: undefined, scope_type: undefined, market: undefined, page: 1, page_size: 50 },
    });
    expect(result.pageSize).toBe(50);
    expect(result.items[0]).toMatchObject({ sourceType: 'rss', scopeType: 'market', lastStatus: 'ok', lastFetchedAt: '2026-07-19' });
  });

  it('creates a source with a snake_case payload', async () => {
    post.mockResolvedValueOnce({ data: { id: 7, name: 'B', source_type: 'rss', url: 'https://b', enabled: true, scope_type: 'stock', scope_value: '600519', market: 'cn' } });

    const created = await intelligenceApi.createSource({
      name: 'B',
      url: 'https://b',
      sourceType: 'rss',
      enabled: true,
      scopeType: 'stock',
      scopeValue: '600519',
      market: 'cn',
    });

    expect(post).toHaveBeenCalledWith('/api/v1/intelligence/sources', {
      name: 'B',
      url: 'https://b',
      source_type: 'rss',
      enabled: true,
      scope_type: 'stock',
      scope_value: '600519',
      market: 'cn',
      description: undefined,
    });
    expect(created).toMatchObject({ id: 7, scopeValue: '600519' });
  });

  it('lists built-in templates', async () => {
    get.mockResolvedValueOnce({ data: { items: [{ template_id: 't1', name: 'T', source_type: 'rss', url: 'https://t', scope_type: 'market', market: 'cn' }], total: 1 } });
    const result = await intelligenceApi.listTemplates();
    expect(get).toHaveBeenCalledWith('/api/v1/intelligence/sources/templates');
    expect(result.items[0]).toMatchObject({ templateId: 't1', sourceType: 'rss' });
  });

  it('creates a source from a template with an encoded id', async () => {
    post.mockResolvedValueOnce({ data: { id: 9, name: 'T', source_type: 'rss', url: 'https://t', enabled: true, scope_type: 'market', market: 'cn' } });
    await intelligenceApi.createSourceFromTemplate('cn/rss news', { enabled: false });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/intelligence/sources/templates/cn%2Frss%20news',
      { name: undefined, enabled: false, scope_type: undefined, scope_value: undefined, market: undefined, description: undefined },
    );
  });

  it('creates default sources', async () => {
    post.mockResolvedValueOnce({ data: { items: [{ created: true, source: { id: 1, name: 'D', source_type: 'rss', url: 'https://d', enabled: true, scope_type: 'market', market: 'cn' } }], created_count: 1, total: 1 } });
    const result = await intelligenceApi.createDefaultSources(true);
    expect(post).toHaveBeenCalledWith('/api/v1/intelligence/sources/defaults', { enabled: true });
    expect(result.createdCount).toBe(1);
    expect(result.items[0].source).toMatchObject({ sourceType: 'rss' });
  });

  it('dry-runs a source payload via test', async () => {
    post.mockResolvedValueOnce({ data: { ok: true, source: { name: 'B' }, fetched_count: 3, sample_items: [{ title: 'x', url: 'https://x', published_at: '2026-07-19' }] } });
    const result = await intelligenceApi.testSource({ name: 'B', url: 'https://b' });
    expect(post).toHaveBeenCalledWith('/api/v1/intelligence/sources/test', expect.objectContaining({ name: 'B', url: 'https://b' }));
    expect(result.fetchedCount).toBe(3);
    expect(result.sampleItems[0]).toMatchObject({ title: 'x', publishedAt: '2026-07-19' });
  });

  it('fetches one source with a dry_run flag', async () => {
    post.mockResolvedValueOnce({ data: { ok: true, source_id: 5, fetched_count: 2, saved_count: 0, dry_run: true, sample_items: [] } });
    const result = await intelligenceApi.fetchSource(5, true);
    expect(post).toHaveBeenCalledWith('/api/v1/intelligence/sources/5/fetch', null, { params: { dry_run: true } });
    expect(result).toMatchObject({ sourceId: 5, fetchedCount: 2, dryRun: true });
  });

  it('fetches all enabled sources', async () => {
    post.mockResolvedValueOnce({ data: { ok: true, source_count: 2, fetched_count: 4, saved_count: 4, sample_items: [] } });
    const result = await intelligenceApi.fetchEnabledSources();
    expect(post).toHaveBeenCalledWith('/api/v1/intelligence/sources/fetch-enabled');
    expect(result).toMatchObject({ sourceCount: 2, fetchedCount: 4, savedCount: 4 });
  });

  it('lists persisted items', async () => {
    get.mockResolvedValueOnce({ data: { items: [{ id: 1, source_type: 'rss', title: 'N', url: 'https://n', scope_type: 'market', market: 'cn', published_at: '2026-07-19', source_name: 'A' }], total: 1, page: 1, page_size: 20 } });
    const result = await intelligenceApi.listItems({ page: 1, pageSize: 20 });
    expect(get).toHaveBeenCalledWith('/api/v1/intelligence/items', {
      params: { source_id: undefined, scope_type: undefined, market: undefined, page: 1, page_size: 20 },
    });
    expect(result.items[0]).toMatchObject({ sourceType: 'rss', publishedAt: '2026-07-19', sourceName: 'A' });
  });
});
