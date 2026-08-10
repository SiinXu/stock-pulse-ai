import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { ReportLanguage } from '../../../types/analysis';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { ReportMarkdown } from '../ReportMarkdown';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
    getDetail: vi.fn().mockRejectedValue(new Error('detail unavailable')),
  },
}));

describe('ReportMarkdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  const renderReport = (uiLanguage: 'zh' | 'en', reportLanguage: ReportLanguage) => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, uiLanguage);
    return render(
      <UiLanguageProvider>
        <ReportMarkdown
          recordId={1}
          stockName="Apple"
          stockCode="AAPL"
          reportLanguage={reportLanguage}
          onClose={() => {}}
        />
      </UiLanguageProvider>,
    );
  };

  const createDeferredMarkdown = () => {
    let resolve!: (content: string) => void;
    const promise = new Promise<string>((done) => {
      resolve = done;
    });
    return { promise, resolve };
  };

  it('keeps Chinese chrome around a Chinese report', async () => {
    const markdown = createDeferredMarkdown();
    vi.mocked(historyApi.getMarkdown).mockReturnValue(markdown.promise);

    renderReport('zh', 'zh');

    const copyButton = await screen.findByRole('button', { name: '复制 Markdown 源码' });
    expect(copyButton).toBeDisabled();
    const closeButtons = screen.getAllByRole('button', { name: '关闭' });
    const primaryClose = closeButtons.find((button) => button.getAttribute('data-control') === 'button');
    expect(primaryClose).toBeDefined();
    expect(primaryClose).toHaveClass('control-hit-target');
    markdown.resolve('# 中文报告');
    expect(await screen.findByRole('heading', { name: '中文报告' })).toBeInTheDocument();
    expect(document.querySelector('.report-markdown-prose')).toHaveClass(
      'overflow-hidden',
      'rounded-xl',
    );
    expect(copyButton).toBeEnabled();
  });

  it('keeps Chinese chrome around an English report', async () => {
    const markdown = createDeferredMarkdown();
    vi.mocked(historyApi.getMarkdown).mockReturnValue(markdown.promise);

    renderReport('zh', 'en');

    const copyButton = await screen.findByRole('button', { name: '复制 Markdown 源码' });
    expect(copyButton).toBeDisabled();
    markdown.resolve('# Full report');
    expect(await screen.findByRole('heading', { name: 'Full report' })).toBeInTheDocument();
    expect(copyButton).toBeEnabled();
  });

  it('keeps English chrome around a Chinese report', async () => {
    const markdown = createDeferredMarkdown();
    vi.mocked(historyApi.getMarkdown).mockReturnValue(markdown.promise);

    renderReport('en', 'zh');

    const copyButton = await screen.findByRole('button', { name: 'Copy Markdown Source' });
    expect(copyButton).toBeDisabled();
    expect(copyButton).toHaveAttribute('data-control', 'icon-button');
    expect(copyButton).toHaveClass('control-hit-target');
    expect(screen.getByRole('button', { name: 'Copy Plain Text' })).toHaveAttribute('data-control', 'icon-button');
    markdown.resolve('# 中文报告');
    expect(await screen.findByRole('heading', { name: '中文报告' })).toBeInTheDocument();
    expect(copyButton).toBeEnabled();
  });

  it('keeps English chrome around an English report', async () => {
    const markdown = createDeferredMarkdown();
    vi.mocked(historyApi.getMarkdown).mockReturnValue(markdown.promise);

    renderReport('en', 'en');

    const copyButton = await screen.findByRole('button', { name: 'Copy Markdown Source' });
    expect(copyButton).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Copy Plain Text' })).toBeInTheDocument();
    markdown.resolve('# Full report');
    expect(await screen.findByRole('heading', { name: 'Full report' })).toBeInTheDocument();
    expect(copyButton).toBeEnabled();
  });
});
