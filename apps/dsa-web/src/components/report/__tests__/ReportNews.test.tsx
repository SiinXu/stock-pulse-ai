import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { ReportNews } from '../ReportNews';

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
    expect(screen.getByRole('link', { name: '跳转' })).toHaveClass('min-h-11', 'min-w-11');
    expect(screen.getByText('相关资讯/后续检索')).toBeVisible();
    expect(screen.getByText('来源：报告页补充资讯；是否用于分析以输入数据块为准。')).toBeVisible();
    const newsItem = container.querySelector('.report-news-item');
    expect(newsItem).toBeTruthy();
    expect(newsItem).toHaveClass('bg-card', 'rounded-lg');

    const refreshButton = screen.getByRole('button', { name: '刷新' });
    expect(refreshButton).toHaveClass('ui-touch-target', 'h-6', 'min-w-6');
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
