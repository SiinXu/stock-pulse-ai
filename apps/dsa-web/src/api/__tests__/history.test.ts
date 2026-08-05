import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../history';
// ci-retrigger: keep history contract tests green under Zod boundary
import { getParsedApiError, isApiRequestError } from '../error';

const { get, delete: del } = vi.hoisted(() => ({
  get: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, delete: del },
  locallyRecoverableResourceConfig: () => ({}),
}));

describe('historyApi.getList', () => {
  beforeEach(() => get.mockReset());

  it('requests history with snake_case filters and camelCases items (pass-through extras)', async () => {
    get.mockResolvedValue({
      data: {
        total: 1,
        page: 1,
        limit: 20,
        unexpected_list_field: 'keep-me',
        items: [{
          id: 9,
          query_id: 'q1',
          stock_code: '600519',
          stock_name: 'Moutai',
          created_at: '2026-01-01T00:00:00Z',
          unexpected_item_field: 'also',
        }],
      },
    });

    const list = await historyApi.getList({ stockCode: '600519', page: 1, limit: 20 });
    expect(get).toHaveBeenCalledWith('/api/v1/history', {
      params: { page: 1, limit: 20, stock_code: '600519' },
    });
    expect(list).toEqual({
      total: 1,
      page: 1,
      limit: 20,
      items: [{
        id: 9,
        queryId: 'q1',
        stockCode: '600519',
        stockName: 'Moutai',
        createdAt: '2026-01-01T00:00:00Z',
        unexpectedItemField: 'also',
      }],
    });
  });

  it('defaults optional items to [] when the contract omits them', async () => {
    get.mockResolvedValue({
      data: { total: 0, page: 1, limit: 20 },
    });
    const list = await historyApi.getList();
    expect(list.items).toEqual([]);
  });

  it('surfaces list shape mismatches through ParsedApiError', async () => {
    get.mockResolvedValue({
      data: {
        // total/page/limit missing
        items: [],
      },
    });

    await expect(historyApi.getList()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('HistoryListResponse');
      return true;
    });
  });
});

describe('historyApi.getDetail / getNews / getMarkdown', () => {
  beforeEach(() => get.mockReset());

  it('validates AnalysisReport detail and rejects missing meta', async () => {
    get.mockResolvedValueOnce({
      data: {
        meta: {
          query_id: 'q1',
          stock_code: '600519',
          stock_name: 'Moutai',
        },
        summary: {
          analysis_summary: 'ok',
          sentiment_score: 70,
        },
        unexpected_root: true,
      },
    });

    const report = await historyApi.getDetail(1);
    expect(report.meta.stockCode).toBe('600519');
    expect(report.summary.sentimentScore).toBe(70);
    expect((report as { unexpectedRoot?: boolean }).unexpectedRoot).toBe(true);

    get.mockResolvedValueOnce({
      data: {
        summary: { analysis_summary: 'no meta' },
      },
    });

    await expect(historyApi.getDetail(1)).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'AnalysisReport' });
      return true;
    });
  });

  it('validates news and markdown responses', async () => {
    get.mockResolvedValueOnce({
      data: {
        total: 1,
        items: [{ title: 'T', snippet: 'S', url: 'https://example.com' }],
      },
    });
    const news = await historyApi.getNews(3, 10);
    expect(get).toHaveBeenCalledWith('/api/v1/history/3/news', { params: { limit: 10 } });
    expect(news.items[0].title).toBe('T');

    get.mockResolvedValueOnce({
      data: { content: '# Report' },
    });
    const md = await historyApi.getMarkdown(3);
    expect(md).toBe('# Report');

    get.mockResolvedValueOnce({
      data: { total: 0 },
    });
    const emptyNews = await historyApi.getNews(3);
    expect(emptyNews.items).toEqual([]);

    get.mockResolvedValueOnce({
      data: { /* content missing */ },
    });
    await expect(historyApi.getMarkdown(3)).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'MarkdownReportResponse' });
      return true;
    });
  });
});

describe('historyApi diagnostics / flow / delete / stock bar', () => {
  beforeEach(() => {
    get.mockReset();
    del.mockReset();
  });

  it('validates diagnostics and run-flow snapshots', async () => {
    get.mockResolvedValueOnce({
      data: {
        status: 'normal',
        status_label: 'OK',
        reason: 'none',
        copy_text: 'trace',
        components: {
          market: {
            key: 'market',
            label: 'Market',
            status: 'ok',
            message: 'fine',
          },
        },
      },
    });
    const diag = await historyApi.getDiagnostics(5);
    expect(diag.statusLabel).toBe('OK');
    expect(diag.copyText).toBe('trace');

    get.mockResolvedValueOnce({
      data: {
        task_id: 't1',
        stock_code: 'AAPL',
        status: 'success',
        generated_at: '2026-01-01T00:00:00Z',
        schema_version: 'run-flow-v1',
        summary: {
          data_source_count: 1,
          event_count: 2,
          failed_attempts: 0,
          fallback_count: 0,
        },
      },
    });
    const flow = await historyApi.getRecordFlow(5);
    expect(flow.taskId).toBe('t1');
    expect(flow.summary.dataSourceCount).toBe(1);

    get.mockResolvedValueOnce({
      data: {
        task_id: 't1',
        // stock_code / summary missing
        status: 'success',
        generated_at: '2026-01-01T00:00:00Z',
        schema_version: 'run-flow-v1',
      },
    });
    await expect(historyApi.getRecordFlow(5)).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'RunFlowSnapshot' });
      return true;
    });
  });

  it('validates delete and stock-bar responses', async () => {
    del.mockResolvedValueOnce({ data: { deleted: 2 } });
    const deleted = await historyApi.deleteRecords([1, 2]);
    expect(deleted.deleted).toBe(2);

    del.mockResolvedValueOnce({ data: { deleted: 3 } });
    const byCode = await historyApi.deleteByCode('600519');
    expect(byCode.deleted).toBe(3);

    del.mockResolvedValueOnce({ data: {} });
    await expect(historyApi.deleteRecords([1])).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'DeleteHistoryResponse' });
      return true;
    });

    get.mockResolvedValueOnce({
      data: {
        total: 1,
        items: [{
          id: 1,
          stock_code: '600519',
          analysis_count: 4,
          stock_name: 'Moutai',
        }],
      },
    });
    const bar = await historyApi.getStockBarList({ limit: 10 });
    expect(bar.items[0].stockCode).toBe('600519');
    expect(bar.items[0].analysisCount).toBe(4);
  });
});
