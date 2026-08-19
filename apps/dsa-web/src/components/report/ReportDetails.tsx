import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import type { ReportDetails as ReportDetailsType, ReportLanguage } from '../../types/analysis';
import { Badge, Button, Card, Collapsible, InlineAlert, useClipboard } from '../common';
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
            size="default"
            onClick={() => copyToClipboard(jsonStr, panel)}
            aria-label={copiedPanels[panel] ? text.copied : text.copy}
          >
            {copiedPanels[panel] ? text.copied : text.copy}
          </Button>
        </span>
        <pre className="max-h-80 w-0 min-w-full overflow-x-auto overflow-y-auto rounded-lg border border-border bg-base p-3 text-left font-mono text-xs text-secondary-text">
          {jsonStr}
        </pre>
      </div>
    );
  };

  return (
    <Card level="interactive" padding="md" className="text-left">
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

      {/* Tertiary JSON blobs stay collapsed by default. */}
      <div className="space-y-3">
        {details?.rawResult && (
          <Collapsible title={text.rawResult} defaultOpen={false}>
            {renderJson(details.rawResult, 'raw')}
          </Collapsible>
        )}

        {details?.contextSnapshot && (
          <Collapsible title={text.analysisSnapshot} defaultOpen={false}>
            {renderJson(details.contextSnapshot, 'snapshot')}
          </Collapsible>
        )}
      </div>
    </Card>
  );
};
