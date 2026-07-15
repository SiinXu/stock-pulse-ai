import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../../i18n/uiText';
import type { ReportLanguage } from '../../../types/analysis';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { ReportDetails } from '../ReportDetails';
import { ReportStrategy } from '../ReportStrategy';

describe('report language boundary', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it.each([
    ['zh', 'zh', '狙击点位', '数据追溯'],
    ['zh', 'en', 'Action Levels', '数据追溯'],
    ['en', 'zh', '狙击点位', 'Data Traceability'],
    ['en', 'en', 'Action Levels', 'Data Traceability'],
  ] as const)(
    'renders %s UI around %s report sections',
    (uiLanguage: UiLanguage, reportLanguage: ReportLanguage, reportSectionTitle, chromeTitle) => {
      window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, uiLanguage);

      render(
        <UiLanguageProvider>
          <ReportStrategy
            language={reportLanguage}
            strategy={{ idealBuy: '10', secondaryBuy: '9', stopLoss: '8', takeProfit: '12' }}
          />
          <ReportDetails
            language={reportLanguage}
            recordId={7}
            details={{ rawResult: { source: 'third-party-original' } }}
          />
        </UiLanguageProvider>,
      );

      expect(screen.getByText(reportSectionTitle)).toBeInTheDocument();
      expect(screen.getByText(chromeTitle)).toBeInTheDocument();
    },
  );
});
