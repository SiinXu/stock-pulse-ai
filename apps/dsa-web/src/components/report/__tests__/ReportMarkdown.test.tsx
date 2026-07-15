import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../../i18n/uiText';
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
    window.localStorage.clear();
  });

  it.each([
    ['zh', 'zh', '复制 Markdown 源码', '关闭', '中文报告正文'],
    ['zh', 'en', '复制 Markdown 源码', '关闭', 'English report body'],
    ['en', 'zh', 'Copy Markdown Source', 'Close', '中文报告正文'],
    ['en', 'en', 'Copy Markdown Source', 'Close', 'English report body'],
  ] as const)(
    'uses %s UI chrome around a %s report',
    async (uiLanguage: UiLanguage, reportLanguage: ReportLanguage, copyLabel, closeLabel, bodyHeading) => {
      window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, uiLanguage);
      vi.mocked(historyApi.getMarkdown).mockResolvedValue(`# ${bodyHeading}`);

      render(
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

      expect(await screen.findByRole('heading', { name: bodyHeading })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: copyLabel })).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: closeLabel }).length).toBeGreaterThan(0);
    },
  );
});
