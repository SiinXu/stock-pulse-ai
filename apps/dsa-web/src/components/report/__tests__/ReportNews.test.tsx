// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { ReportNews } from '../ReportNews';

const indexCss = fs.readFileSync('src/index.css', 'utf8');

vi.mock('../../../api/history', () => ({
  historyApi: {
    getNews: vi.fn(),
  },
}));

describe('ReportNews', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders news items and refreshes with preserved subpanel styling', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 1,
      items: [
        {
          title: '茅台发布最新经营数据',
          snippet: '公司披露季度经营情况，市场关注度提升。',
          url: 'https://example.com/news',
        },
      ],
    });

    const { container } = render(<ReportNews recordId={1} />);

    expect(await screen.findByText('茅台发布最新经营数据')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '跳转' })).toHaveAttribute('href', 'https://example.com/news');
    expect(screen.getByRole('link', { name: '跳转' })).toHaveClass('control-hit-target');
    expect(screen.getByText('相关资讯/后续检索')).toBeVisible();
    expect(screen.getByText('来源：报告页补充资讯；是否用于分析以输入数据块为准。')).toBeVisible();
    expect(container.querySelector('[data-surface-level="interactive"]')).toBeTruthy();
    expect(container.querySelector('.report-news-item')).toBeTruthy();
    expect(indexCss).toMatch(/\.report-news-item\s*\{/);
    expect(indexCss).toMatch(/\.report-news-title\s*\{/);
    expect(indexCss).toMatch(/\.report-news-snippet\s*\{/);
    expect(indexCss).toMatch(/\.dark\s+\.report-news-item\s*\{/);

    const refreshButton = screen.getByRole('button', { name: '刷新' });
    expect(refreshButton).toHaveAttribute('data-control', 'button');
    expect(refreshButton).toHaveClass('control-hit-target');
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(historyApi.getNews).toHaveBeenCalledTimes(2);
    });
  });

  it('renders the empty state when no news exists', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 0,
      items: [],
    });

    render(<ReportNews recordId={1} />);

    expect(await screen.findByText('暂无相关资讯')).toBeInTheDocument();
    expect(screen.getByText('可稍后刷新以获取最新资讯。')).toBeInTheDocument();
  });

  it('uses one live status while the header spinner remains decorative', async () => {
    let resolveRequest!: (
      value: Awaited<ReturnType<typeof historyApi.getNews>>,
    ) => void;
    const pendingRequest = new Promise<Awaited<ReturnType<typeof historyApi.getNews>>>(
      (resolve) => {
        resolveRequest = resolve;
      },
    );
    vi.mocked(historyApi.getNews).mockReturnValue(pendingRequest);

    const { container } = render(<ReportNews recordId={1} />);

    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(screen.getByRole('status')).toHaveTextContent('加载资讯中...');
    expect(container.querySelector('[data-control="spinner"]')).toHaveAttribute(
      'aria-hidden',
      'true',
    );

    await act(async () => {
      resolveRequest({ total: 0, items: [] });
      await pendingRequest;
    });
  });

  it('keeps UI-owned empty state Chinese around an English report section', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 0,
      items: [],
    });

    render(<ReportNews recordId={1} language="en" />);

    expect(await screen.findByText('暂无相关资讯')).toBeInTheDocument();
    expect(screen.getByText('可稍后刷新以获取最新资讯。')).toBeInTheDocument();
    expect(screen.getByText('Related news / follow-up retrieval')).toBeVisible();
  });

  it('keeps UI-owned empty state English around a Chinese report section', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 0,
      items: [],
    });
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');

    render(
      <UiLanguageProvider>
        <ReportNews recordId={1} language="zh" />
      </UiLanguageProvider>,
    );

    expect(await screen.findByText('No related news')).toBeInTheDocument();
    expect(screen.getByText('Refresh later to check for the latest updates.')).toBeInTheDocument();
    expect(screen.getByText('相关资讯/后续检索')).toBeVisible();
  });

  it('renders the error state and supports retry', async () => {
    vi.mocked(historyApi.getNews)
      .mockRejectedValueOnce(new Error('network failed'))
      .mockResolvedValueOnce({
        total: 1,
        items: [
          {
            title: '重试成功',
            snippet: '第二次请求成功返回。',
            url: 'https://example.com/retry',
          },
        ],
      });

    render(<ReportNews recordId={1} />);

    expect(await screen.findByRole('alert')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    expect(await screen.findByText('重试成功')).toBeInTheDocument();
  });
});
