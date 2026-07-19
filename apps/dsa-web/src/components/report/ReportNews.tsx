import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { ExternalLink, Newspaper } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import { ApiErrorAlert, Badge, Button, Card, Spinner, StatePanel, Surface } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { historyApi } from '../../api/history';
import type { NewsIntelItem, ReportLanguage } from '../../types/analysis';
import { REPORT_NEWS_CONTENT_TEXT } from '../../locales/reportContent';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

interface ReportNewsProps {
  recordId?: number;  // Analysis history record ID.
  limit?: number;
  language?: ReportLanguage;
}

/** Related-news panel. */
export const ReportNews: React.FC<ReportNewsProps> = ({ recordId, limit = 8, language = 'zh' }) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const { language: uiLanguage, t } = useUiLanguage();
  const chromeText = REPORT_CHROME_TEXT[uiLanguage];
  const sourceText = REPORT_NEWS_CONTENT_TEXT[reportLanguage];
  const [isLoading, setIsLoading] = useState(false);
  const [items, setItems] = useState<NewsIntelItem[]>([]);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const fetchNews = useCallback(async () => {
    if (!recordId) return;
    setIsLoading(true);
    setError(null);

    try {
      const response = await historyApi.getNews(recordId, limit);
      setItems(response.items || []);
    } catch (err) {
      setError(getParsedApiError(err, uiLanguage));
    } finally {
      setIsLoading(false);
    }
  }, [recordId, limit, uiLanguage]);

  useEffect(() => {
    setItems([]);
    setError(null);

    if (recordId) {
      fetchNews();
    }
  }, [recordId, fetchNews]);

  if (!recordId) {
    return null;
  }

  return (
    <Card variant="bordered" padding="md">
      <DashboardPanelHeader
        eyebrow={text.newsFeed}
        title={text.relatedNews}
        actions={(
          <div className="flex items-center gap-2">
            {isLoading ? (
              <Spinner size="sm" />
            ) : null}
            <Badge variant="default" size="sm">
              {sourceText.sourceLabel}
            </Badge>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void fetchNews()}
              className="min-h-11 min-w-11 text-xs"
              aria-label={t('usage.refresh')}
            >
              {t('usage.refresh')}
            </Button>
          </div>
        )}
      />
      <p className="mb-3 text-xs leading-5 text-muted-text">
        {sourceText.sourceHint}
      </p>

      {error && !isLoading && (
        <ApiErrorAlert
          error={error}
          actionLabel={t('common.retry')}
          onAction={() => void fetchNews()}
          dismissLabel={t('taskPanel.dismiss')}
        />
      )}

      {isLoading && !error && (
        <StatePanel status="loading"
          compact
          title={chromeText.loadingNews}
        />
      )}

      {!isLoading && !error && items.length === 0 && (
        <StatePanel status="empty"
          compact
          title={chromeText.noNews}
          description={chromeText.noNewsDescription}
          icon={(
            <Newspaper className="h-4 w-4" aria-hidden="true" />
          )}
        />
      )}

      {!isLoading && !error && items.length > 0 && (
        <div className="space-y-3 text-left">
          {items.map((item, index) => (
            <Surface
              key={`${item.title}-${index}`}
              variant="subtle"
              radius="md"
              padding="md"
              className="report-news-item group"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0 text-left">
                  <p className="report-news-title text-left text-sm font-medium leading-6 text-foreground">
                    {item.title}
                  </p>
                  {item.snippet && (
                    <p className="report-news-snippet mt-2 overflow-hidden text-left text-sm leading-6 text-secondary-text [display:-webkit-box] [-webkit-line-clamp:3] [-webkit-box-orient:vertical]">
                      {item.snippet}
                    </p>
                  )}
                </div>
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-1 whitespace-nowrap rounded-lg border border-border bg-hover px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-subtle-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/15"
                    aria-label={chromeText.openLink}
                  >
                    {chromeText.openLink}
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
              </div>
            </Surface>
          ))}

        </div>
      )}
    </Card>
  );
};
