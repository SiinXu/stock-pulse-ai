// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useState } from 'react';
import { Braces, Package } from 'lucide-react';
import { getParsedApiError } from '../../api/error';
import { evidencePackExportApi } from '../../api/evidencePackExport';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVIDENCE_PACK_EXPORT_TEXT } from '../../locales/evidencePackExport';
import { buildSettingsHref } from '../../routing/routes';
import { Button } from '../common/Button';
import { InlineAlert } from '../common/InlineAlert';

export interface EvidencePackExportControlsProps {
  recordId: number; className?: string; disabled?: boolean;
}
type Feedback = { kind: 'disabled' | 'error' | 'truncated'; message: string } | null;
type ExportKind = 'zip' | 'chain';

function isExportDisabledError(code: string | undefined): boolean {
  return code === 'audit_export_disabled' || code === 'evidence_chain_disabled';
}

const EvidencePackExportControls: React.FC<EvidencePackExportControlsProps> = ({
  recordId, className, disabled = false,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = EVIDENCE_PACK_EXPORT_TEXT[uiLanguage];
  const [exporting, setExporting] = useState<ExportKind | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const settingsHref = buildSettingsHref({ section: 'agent_behavior', view: 'execution' });

  const handleExport = useCallback(async (kind: ExportKind) => {
    setFeedback(null); setExporting(kind);
    try {
      const result = kind === 'zip'
        ? await evidencePackExportApi.downloadAuditPackage(recordId, 'zip')
        : await evidencePackExportApi.downloadEvidenceChain(recordId);
      if (result.truncated) setFeedback({ kind: 'truncated', message: text.exportTruncated });
    } catch (error) {
      const parsed = getParsedApiError(error, uiLanguage);
      if (isExportDisabledError(parsed.code)) {
        setFeedback({ kind: 'disabled', message: parsed.message || text.exportDisabled });
      } else {
        setFeedback({ kind: 'error', message: parsed.message || text.exportFailed });
      }
    } finally { setExporting(null); }
  }, [recordId, text.exportDisabled, text.exportFailed, text.exportTruncated, uiLanguage]);

  const controlsDisabled = disabled || exporting !== null;
  return (
    <div className={className} data-testid="evidence-pack-export-controls">
      <div className="space-y-2 rounded-lg border border-border bg-card p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{text.exportAuditPackageZip}</p>
            <p className="mt-1 text-xs leading-5 text-secondary-text">{text.exportHint}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" size="compact" onClick={() => { void handleExport('chain'); }} disabled={controlsDisabled} data-testid="evidence-chain-export-json">
              <Braces className="h-3.5 w-3.5" aria-hidden="true" />
              {exporting === 'chain' ? text.exportBusy : text.exportEvidenceChainJson}
            </Button>
            <Button type="button" variant="secondary" size="compact" onClick={() => { void handleExport('zip'); }} disabled={controlsDisabled} data-testid="audit-package-export-zip">
              <Package className="h-3.5 w-3.5" aria-hidden="true" />
              {exporting === 'zip' ? text.exportBusy : text.exportAuditPackageZip}
            </Button>
          </div>
        </div>
      </div>
      {feedback?.kind === 'disabled' ? (
        <InlineAlert variant="warning" className="mt-3" data-testid="evidence-pack-export-disabled" message={(
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{feedback.message}</span>
            <a href={settingsHref} className="font-medium text-primary underline-offset-2 hover:underline" data-testid="evidence-pack-export-settings-link">{text.exportDisabledLink}</a>
          </span>
        )} />
      ) : null}
      {feedback?.kind === 'error' ? <InlineAlert variant="danger" className="mt-3" message={feedback.message} data-testid="evidence-pack-export-error" /> : null}
      {feedback?.kind === 'truncated' ? <InlineAlert variant="warning" className="mt-3" message={feedback.message} data-testid="evidence-pack-export-truncated" /> : null}
    </div>
  );
};
export default EvidencePackExportControls;
