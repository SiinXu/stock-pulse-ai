// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Download, FileCode, FileDown } from 'lucide-react';
import { getParsedApiError } from '../../api/error';
import { reportExportApi, type ReportExportFormat } from '../../api/reportExport';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import { cn } from '../../utils/cn';
import { IconButton } from '../common/IconButton';
import { InlineAlert } from '../common/InlineAlert';

export interface ReportExportDownloadButtonsProps {
  recordId: number;
  disabled?: boolean;
  className?: string;
}

const ReportExportDownloadButtons: React.FC<ReportExportDownloadButtonsProps> = ({
  recordId,
  disabled = false,
  className,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const [exporting, setExporting] = useState<ReportExportFormat | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [htmlAvailable, setHtmlAvailable] = useState(false);
  const [pdfAvailable, setPdfAvailable] = useState(false);

  const handleExport = useCallback(async (format: ReportExportFormat) => {
    setExportError(null);
    setExporting(format);
    try {
      await reportExportApi.download(recordId, format);
    } catch (error) {
      const parsed = getParsedApiError(error, uiLanguage);
      setExportError(parsed.message || text.downloadFailed);
    } finally {
      setExporting(null);
    }
  }, [recordId, text.downloadFailed, uiLanguage]);

  useEffect(() => {
    let active = true;
    reportExportApi.getCapabilities(uiLanguage === 'zh' ? 'zh' : 'en')
      .then((caps) => {
        if (active) {
          setHtmlAvailable(Boolean(caps.formats.html?.available));
          setPdfAvailable(Boolean(caps.formats.pdf.available));
        }
      })
      .catch(() => {
        if (active) {
          setHtmlAvailable(false);
          setPdfAvailable(false);
        }
      });
    return () => {
      active = false;
    };
  }, [uiLanguage]);

  const controlsDisabled = disabled || exporting !== null;

  return (
    <div className={cn('flex flex-col items-end gap-2', className)} data-testid="report-export-controls">
      <div className="flex items-center gap-3">
        <IconButton
          type="button"
          variant="outline"
          size="default"
          onClick={() => { void handleExport('md'); }}
          disabled={controlsDisabled}
          aria-label={text.downloadMarkdown}
          data-testid="report-export-md"
        >
          <Download aria-hidden="true" />
        </IconButton>

        <IconButton
          type="button"
          variant="outline"
          size="default"
          onClick={() => { void handleExport('html'); }}
          disabled={controlsDisabled || !htmlAvailable}
          aria-label={htmlAvailable ? text.downloadHtml : text.downloadHtmlUnavailable}
          title={htmlAvailable ? text.downloadHtml : text.downloadHtmlUnavailable}
          data-testid="report-export-html"
        >
          <FileCode aria-hidden="true" />
        </IconButton>

        <IconButton
          type="button"
          variant="outline"
          size="default"
          onClick={() => { void handleExport('pdf'); }}
          disabled={controlsDisabled || !pdfAvailable}
          aria-label={pdfAvailable ? text.downloadPdf : text.downloadPdfUnavailable}
          title={pdfAvailable ? text.downloadPdf : text.downloadPdfUnavailable}
          data-testid="report-export-pdf"
        >
          <FileDown aria-hidden="true" />
        </IconButton>
      </div>
      {exportError ? (
        <InlineAlert
          variant="danger"
          message={exportError}
          className="w-full max-w-sm"
          data-testid="report-export-error"
        />
      ) : null}
    </div>
  );
};

export default ReportExportDownloadButtons;
