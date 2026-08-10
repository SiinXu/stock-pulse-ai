import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Check, Code2, ExternalLink, FileText } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { historyApi } from '../../api/history';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import type { AnalysisReport, ReportLanguage } from '../../types/analysis';
import { markdownToPlainText } from '../../utils/markdown';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import { ApiErrorAlert } from '../common/ApiErrorAlert';
import { Button } from '../common/Button';
import { IconButton } from '../common/IconButton';
import { InlineAlert } from '../common/InlineAlert';
import { Spinner } from '../common/Spinner';
import { useClipboard } from '../common/useClipboard';
import { ReportDecisionCard } from './ReportDecisionCard';
import { ReportMarkdownBody } from './ReportMarkdownBody';
import { ShareImageButton } from './ShareImageButton';

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
  reportLanguage,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const reportText = getReportText(normalizeReportLanguage(reportLanguage));
  const [content, setContent] = useState<string>('');
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [copiedType, setCopiedType] = useState<'markdown' | 'text' | null>(null);
  const { copyText, copyError } = useClipboard();

  const fullReportHref = buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    recordId,
  });

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

    const fetchReportSurfaces = async () => {
      setIsLoading(true);
      setError(null);
      setReport(null);
      try {
        const [markdownResult, detailResult] = await Promise.allSettled([
          historyApi.getMarkdown(recordId),
          historyApi.getDetail(recordId),
        ]);

        if (!isMounted) {
          return;
        }

        if (markdownResult.status === 'rejected') {
          setError(getParsedApiError(markdownResult.reason, uiLanguage));
          setContent('');
          return;
        }

        setContent(markdownResult.value);
        if (detailResult.status === 'fulfilled') {
          setReport(detailResult.value);
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

    fetchReportSurfaces();

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

        <div className="flex items-center gap-3">
          <ShareImageButton
            recordId={recordId}
            reportTitle={`${stockName || stockCode}-${stockCode}`}
            reportLanguage={reportLanguage}
          />
          <IconButton
            type="button"
            variant="outline"
            size="default"
            onClick={handleCopyMarkdown}
            disabled={isLoading || !content || copiedType !== null}
            aria-label={text.copyMarkdownSource}
          >
            {copiedType === 'markdown' ? (
              <Check className="text-success" aria-hidden="true" />
            ) : (
              <Code2 aria-hidden="true" />
            )}
          </IconButton>

          <IconButton
            type="button"
            variant="outline"
            size="default"
            onClick={handleCopyPlainText}
            disabled={isLoading || !content || copiedType !== null}
            aria-label={text.copyPlainText}
          >
            {copiedType === 'text' ? (
              <Check className="text-success" aria-hidden="true" />
            ) : (
              <FileText aria-hidden="true" />
            )}
          </IconButton>
        </div>
      </div>

      {copyError ? <InlineAlert variant="danger" message={copyError} className="mb-4" /> : null}

      {isLoading ? (
        <div className="flex h-64 flex-col items-center justify-center">
          <Spinner size="lg" label={text.loadingReport} />
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
        <div className="space-y-4">
          {report ? (
            <ReportDecisionCard
              meta={report.meta}
              summary={report.summary}
              strategy={report.strategy}
              details={report.details}
              language={normalizeReportLanguage(reportLanguage ?? report.meta.reportLanguage)}
              compact
            />
          ) : null}

          <p className="text-xs text-muted-text">
            <a
              href={fullReportHref}
              className="inline-flex items-center gap-1 font-medium text-primary underline-offset-2 hover:underline"
              data-testid="report-markdown-open-full-page"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              {reportText.openFullReportPage}
            </a>
          </p>

          <ReportMarkdownBody content={content} />
        </div>
      )}

      <div className="mt-6 flex justify-end border-t border-border pt-4">
        <Button
          type="button"
          variant="secondary"
          size="default"
          onClick={onRequestClose}
        >
          {text.dismiss}
        </Button>
      </div>
    </>
  );
};
