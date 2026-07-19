import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ReportDetails as ReportDetailsType, ReportLanguage } from '../../types/analysis';
import { Badge, Button, Card, InlineAlert, useClipboard } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';

interface ReportDetailsProps {
  details?: ReportDetailsType;
  recordId?: number;  // Analysis history record ID.
  language?: ReportLanguage;
}

/** Transparency and traceability panel. */
export const ReportDetails: React.FC<ReportDetailsProps> = ({
  details,
  recordId,
}) => {
  type JsonPanel = 'raw' | 'snapshot';
  type CopiedPanelState = Record<JsonPanel, boolean>;

  const { language: uiLanguage } = useUiLanguage();
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const [showRaw, setShowRaw] = useState(false);
  const [showSnapshot, setShowSnapshot] = useState(false);
  const [copiedPanels, setCopiedPanels] = useState<CopiedPanelState>({
    raw: false,
    snapshot: false,
  });
  const copyResetTimerRef = useRef<Partial<Record<JsonPanel, number>>>({});
  const { copyText, copyError } = useClipboard();

  useEffect(() => {
    return () => {
      Object.values(copyResetTimerRef.current).forEach((timerId) => {
        if (timerId !== undefined) {
          window.clearTimeout(timerId);
        }
      });
      copyResetTimerRef.current = {};
    };
  }, []);

  if (!details?.rawResult && !details?.contextSnapshot && !recordId) {
    return null;
  }

  const copyToClipboard = async (content: string, panel: JsonPanel) => {
    if (await copyText(content)) {
      setCopiedPanels((prev) => ({
        ...prev,
        [panel]: true,
      }));
      const existingTimer = copyResetTimerRef.current[panel];
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }
      copyResetTimerRef.current[panel] = window.setTimeout(() => {
        setCopiedPanels((prev) => ({
          ...prev,
          [panel]: false,
        }));
        delete copyResetTimerRef.current[panel];
      }, 2000);
    }
  };

  const renderJson = (data: unknown, panel: JsonPanel) => {
    const jsonStr = JSON.stringify(data, null, 2);
    return (
      <div className="relative overflow-hidden">
        <span className="absolute top-2 right-2 z-10 inline-flex">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => copyToClipboard(jsonStr, panel)}
            className="text-xs"
            aria-label={copiedPanels[panel] ? text.copied : text.copy}
          >
            {copiedPanels[panel] ? text.copied : text.copy}
          </Button>
        </span>
        <pre className="report-trace-pre report-trace-pre-content max-h-80 w-0 min-w-full overflow-x-auto overflow-y-auto rounded-lg bg-base p-3 text-left font-mono text-xs text-foreground">
          {jsonStr}
        </pre>
      </div>
    );
  };

  return (
    <Card variant="bordered" padding="md" className="text-left">
      <DashboardPanelHeader
        eyebrow={text.transparency}
        title={text.traceability}
        className="mb-3"
      />

      {copyError ? <InlineAlert variant="danger" message={copyError} className="mb-3" /> : null}

      {/* Record ID */}
      {recordId && (
        <div className="mb-3 flex items-center gap-2 border-b border-border pb-3 text-xs text-muted-text">
          <span>{text.recordId}:</span>
          <Badge variant="default" size="sm" className="font-mono">
            {recordId}
          </Badge>
        </div>
      )}

      {/* Collapsible sections */}
      <div className="space-y-2">
        {/* Raw analysis result */}
        {details?.rawResult && (
          <div>
            <Button
              type="button"
              variant="secondary"
              size="xl"
              onClick={() => setShowRaw(!showRaw)}
              className="report-trace-toggle w-full justify-between px-2.5"
              aria-expanded={showRaw}
            >
              <span className="text-xs text-foreground">{text.rawResult}</span>
              <ChevronDown
                className={`h-3.5 w-3.5 text-muted-text transition-transform ${showRaw ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </Button>
            {showRaw && (
              <div className="mt-2 animate-fade-in min-w-0 overflow-hidden">
                {renderJson(details.rawResult, 'raw')}
              </div>
            )}
          </div>
        )}

        {/* Analysis snapshot */}
        {details?.contextSnapshot && (
          <div>
            <Button
              type="button"
              variant="secondary"
              size="xl"
              onClick={() => setShowSnapshot(!showSnapshot)}
              className="report-trace-toggle w-full justify-between px-2.5"
              aria-expanded={showSnapshot}
            >
              <span className="text-xs text-foreground">{text.analysisSnapshot}</span>
              <ChevronDown
                className={`h-3.5 w-3.5 text-muted-text transition-transform ${showSnapshot ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </Button>
            {showSnapshot && (
              <div className="mt-2 animate-fade-in min-w-0 overflow-hidden">
                {renderJson(details.contextSnapshot, 'snapshot')}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
