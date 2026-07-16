import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { historyApi } from '../../api/history';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import type { ReportLanguage } from '../../types/analysis';
import { markdownToPlainText } from '../../utils/markdown';
import { Tooltip } from '../common/Tooltip';
import { ApiErrorAlert } from '../common/ApiErrorAlert';
import { ReportMarkdownBody } from './ReportMarkdownBody';

export interface ReportMarkdownPanelProps {
  recordId: number;
  stockName: string;
  stockCode: string;
  onRequestClose: () => void;
  reportLanguage?: ReportLanguage;
}

export const ReportMarkdownPanel: React.FC<ReportMarkdownPanelProps> = ({
  recordId,
  stockName,
  stockCode,
  onRequestClose,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const [content, setContent] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [copiedType, setCopiedType] = useState<'markdown' | 'text' | null>(null);

  const handleCopyMarkdown = useCallback(async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopiedType('markdown');
      setTimeout(() => setCopiedType(null), 2000);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  }, [content]);

  const handleCopyPlainText = useCallback(async () => {
    if (!content) return;
    try {
      const plainText = markdownToPlainText(content);
      await navigator.clipboard.writeText(plainText);
      setCopiedType('text');
      setTimeout(() => setCopiedType(null), 2000);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  }, [content]);

  useEffect(() => {
    let isMounted = true;

    const fetchMarkdown = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const markdownContent = await historyApi.getMarkdown(recordId);
        if (isMounted) {
          setContent(markdownContent);
        }
      } catch (err) {
        if (isMounted) {
          setError(getParsedApiError(err, uiLanguage));
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchMarkdown();

    return () => {
      isMounted = false;
    };
  }, [recordId, uiLanguage]);

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex flex-1 items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--home-action-report-bg)] text-[var(--home-action-report-text)]">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{stockName || stockCode}</h2>
            <p className="text-xs text-muted-text">{text.fullReport}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Tooltip content={text.copyMarkdownSource}>
            <span className="inline-flex">
              <button
                type="button"
                onClick={handleCopyMarkdown}
                disabled={isLoading || !content || copiedType !== null}
                className="home-surface-button flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-50"
                aria-label={text.copyMarkdownSource}
              >
                {copiedType === 'markdown' ? (
                  <svg className="h-6 w-6 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                )}
              </button>
            </span>
          </Tooltip>

          <Tooltip content={text.copyPlainText}>
            <span className="inline-flex">
              <button
                type="button"
                onClick={handleCopyPlainText}
                disabled={isLoading || !content || copiedType !== null}
                className="home-surface-button flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-50"
                aria-label={text.copyPlainText}
              >
                {copiedType === 'text' ? (
                  <svg className="h-6 w-6 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                )}
              </button>
            </span>
          </Tooltip>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 flex-col items-center justify-center">
          <div className="home-spinner h-10 w-10 animate-spin border-[3px]" />
          <p className="mt-4 text-sm text-secondary-text">{text.loadingReport}</p>
        </div>
      ) : error ? (
        <div className="flex h-64 flex-col items-center justify-center">
          <ApiErrorAlert
            error={error}
            className="w-full max-w-lg"
            dismissLabel={text.dismiss}
            onDismiss={onRequestClose}
          />
        </div>
      ) : (
        <ReportMarkdownBody content={content} />
      )}

      <div className="home-divider mt-6 flex justify-end border-t pt-4">
        <button
          type="button"
          onClick={onRequestClose}
          className="home-surface-button min-h-11 min-w-11 rounded-lg px-4 py-2 text-sm text-secondary-text hover:text-foreground"
        >
          {text.dismiss}
        </button>
      </div>
    </>
  );
};
