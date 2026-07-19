import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Check, Code2, FileText } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { historyApi } from '../../api/history';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import type { ReportLanguage } from '../../types/analysis';
import { markdownToPlainText } from '../../utils/markdown';
import { ApiErrorAlert } from '../common/ApiErrorAlert';
import { Button } from '../common/Button';
import { IconButton } from '../common/IconButton';
import { InlineAlert } from '../common/InlineAlert';
import { Spinner } from '../common/Spinner';
import { useClipboard } from '../common/useClipboard';
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
  const { copyText, copyError } = useClipboard();

  const handleCopyMarkdown = useCallback(async () => {
    if (!content) return;
    if (await copyText(content)) {
      setCopiedType('markdown');
      setTimeout(() => setCopiedType(null), 2000);
    }
  }, [content, copyText]);

  const handleCopyPlainText = useCallback(async () => {
    if (!content) return;
    const plainText = markdownToPlainText(content);
    if (await copyText(plainText)) {
      setCopiedType('text');
      setTimeout(() => setCopiedType(null), 2000);
    }
  }, [content, copyText]);

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
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-hover text-secondary-text">
            <FileText className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{stockName || stockCode}</h2>
            <p className="text-xs text-muted-text">{text.fullReport}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <IconButton
                type="button"
                onClick={handleCopyMarkdown}
                disabled={isLoading || !content || copiedType !== null}
                aria-label={text.copyMarkdownSource}
                tooltip={text.copyMarkdownSource}
              >
                {copiedType === 'markdown' ? (
                  <Check className="h-6 w-6 text-success" aria-hidden="true" />
                ) : (
                  <Code2 className="h-6 w-6" aria-hidden="true" />
                )}
          </IconButton>

          <IconButton
                type="button"
                onClick={handleCopyPlainText}
                disabled={isLoading || !content || copiedType !== null}
                aria-label={text.copyPlainText}
                tooltip={text.copyPlainText}
              >
                {copiedType === 'text' ? (
                  <Check className="h-6 w-6 text-success" aria-hidden="true" />
                ) : (
                  <FileText className="h-6 w-6" aria-hidden="true" />
                )}
          </IconButton>
        </div>
      </div>

      {copyError ? <InlineAlert variant="danger" message={copyError} className="mb-4" /> : null}

      {isLoading ? (
        <div className="flex h-64 flex-col items-center justify-center">
          <Spinner size="lg" />
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

      <div className="mt-6 flex justify-end border-t border-border pt-4">
        <Button
          type="button"
          variant="secondary"
          size="md"
          onClick={onRequestClose}
        >
          {text.dismiss}
        </Button>
      </div>
    </>
  );
};
