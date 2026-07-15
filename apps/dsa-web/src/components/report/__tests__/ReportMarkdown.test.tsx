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

  it('keeps Chinese chrome around a Chinese report', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 中文报告');

    renderReport('zh', 'zh');

    expect(await screen.findByRole('button', { name: '复制 Markdown 源码' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '中文报告' })).toBeInTheDocument();
  });

  it('keeps Chinese chrome around an English report', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Full report');

    renderReport('zh', 'en');

    expect(await screen.findByRole('button', { name: '复制 Markdown 源码' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Full report' })).toBeInTheDocument();
  });

  it('keeps English chrome around a Chinese report', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 中文报告');

    renderReport('en', 'zh');

    expect(await screen.findByRole('button', { name: 'Copy Markdown Source' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Plain Text' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '中文报告' })).toBeInTheDocument();
  });

  it('keeps English chrome around an English report', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Full report');

    renderReport('en', 'en');

    expect(await screen.findByRole('button', { name: 'Copy Markdown Source' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Plain Text' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Full report' })).toBeInTheDocument();
  });
});
