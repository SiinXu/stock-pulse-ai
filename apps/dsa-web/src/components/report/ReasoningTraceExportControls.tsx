// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useState } from 'react';
import { Braces, FileText } from 'lucide-react';
import { getParsedApiError } from '../../api/error';
import {
  reasoningTraceExportApi,
  type ReasoningTraceExportFormat,
} from '../../api/reasoningTraceExport';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import { buildSettingsHref } from '../../routing/routes';
import { Button } from '../common/Button';
import { IconButton } from '../common/IconButton';
import { InlineAlert } from '../common/InlineAlert';

export interface ReasoningTraceExportControlsProps {
  recordId: number;
  /** Icon-only toolbar (report panel) vs labeled section (run diagnostics). */
  variant?: 'toolbar' | 'section';
  className?: string;
  disabled?: boolean;
}

type Feedback =
  | { kind: 'disabled'; message: string }
  | { kind: 'error'; message: string }
  | { kind: 'truncated'; message: string }
  | null;

function isExportDisabledError(code: string | undefined): boolean {
  return code === 'reasoning_trace_export_disabled';
}

/**
 * Product entry for opt-in reasoning-trace export.
 *
 * Buttons stay visible when the feature is off; failed export with the
 * disabled error code surfaces an explicit Settings deep link instead of
 * hiding the control or failing silently.
 */
export const ReasoningTraceExportControls: React.FC<ReasoningTraceExportControlsProps> = ({
  recordId,
  variant = 'toolbar',
  className,
  disabled = false,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const [exporting, setExporting] = useState<ReasoningTraceExportFormat | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const settingsHref = buildSettingsHref({
    section: 'agent_behavior',
    view: 'execution',
  });

  const handleExport = useCallback(async (format: ReasoningTraceExportFormat) => {
    setFeedback(null);
    setExporting(format);
    try {
      const result = await reasoningTraceExportApi.download(recordId, format);
      if (result.truncated) {
        setFeedback({ kind: 'truncated', message: text.exportReasoningTraceTruncated });
      }
    } catch (error) {
      const parsed = getParsedApiError(error, uiLanguage);
      if (isExportDisabledError(parsed.code)) {
        setFeedback({
          kind: 'disabled',
          message: parsed.message || text.exportReasoningTraceDisabled,
        });
      } else {
        setFeedback({
          kind: 'error',
          message: parsed.message || text.exportReasoningTraceFailed,
        });
      }
    } finally {
      setExporting(null);
    }
  }, [recordId, text.exportReasoningTraceDisabled, text.exportReasoningTraceFailed, text.exportReasoningTraceTruncated, uiLanguage]);

  const busy = exporting !== null;
  const controlsDisabled = disabled || busy;

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {variant === 'toolbar' ? (
        <>
          <IconButton
            type="button"
            variant="outline"
            size="default"
            onClick={() => { void handleExport('json'); }}
            disabled={controlsDisabled}
            aria-label={exporting === 'json' ? text.exportReasoningTraceBusy : text.exportReasoningTraceJson}
            title={text.exportReasoningTraceJson}
            data-testid="reasoning-trace-export-json"
          >
            <Braces aria-hidden="true" />
          </IconButton>
          <IconButton
            type="button"
            variant="outline"
            size="default"
            onClick={() => { void handleExport('markdown'); }}
            disabled={controlsDisabled}
            aria-label={exporting === 'markdown' ? text.exportReasoningTraceBusy : text.exportReasoningTraceMarkdown}
            title={text.exportReasoningTraceMarkdown}
            data-testid="reasoning-trace-export-markdown"
          >
            <FileText aria-hidden="true" />
          </IconButton>
        </>
      ) : (
        <>
          <Button
            type="button"
            variant="secondary"
            size="compact"
            onClick={() => { void handleExport('json'); }}
            disabled={controlsDisabled}
            data-testid="reasoning-trace-export-json"
          >
            <Braces className="h-3.5 w-3.5" aria-hidden="true" />
            {exporting === 'json' ? text.exportReasoningTraceBusy : text.exportReasoningTraceJson}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="compact"
            onClick={() => { void handleExport('markdown'); }}
            disabled={controlsDisabled}
            data-testid="reasoning-trace-export-markdown"
          >
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            {exporting === 'markdown' ? text.exportReasoningTraceBusy : text.exportReasoningTraceMarkdown}
          </Button>
        </>
      )}
    </div>
  );

  return (
    <div className={className} data-testid="reasoning-trace-export-controls">
      {variant === 'section' ? (
        <div className="space-y-2 rounded-lg border border-border bg-card p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{text.exportReasoningTraceJson}</p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">{text.exportReasoningTraceHint}</p>
            </div>
            {actions}
          </div>
        </div>
      ) : (
        actions
      )}

      {feedback?.kind === 'disabled' ? (
        <InlineAlert
          variant="warning"
          className="mt-3"
          data-testid="reasoning-trace-export-disabled"
          message={(
            <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>{feedback.message}</span>
              <a
                href={settingsHref}
                className="font-medium text-primary underline-offset-2 hover:underline"
                data-testid="reasoning-trace-export-settings-link"
              >
                {text.exportReasoningTraceDisabledLink}
              </a>
            </span>
          )}
        />
      ) : null}

      {feedback?.kind === 'error' ? (
        <InlineAlert
          variant="danger"
          className="mt-3"
          message={feedback.message}
          data-testid="reasoning-trace-export-error"
        />
      ) : null}

      {feedback?.kind === 'truncated' ? (
        <InlineAlert
          variant="warning"
          className="mt-3"
          message={feedback.message}
          data-testid="reasoning-trace-export-truncated"
        />
      ) : null}
    </div>
  );
};
