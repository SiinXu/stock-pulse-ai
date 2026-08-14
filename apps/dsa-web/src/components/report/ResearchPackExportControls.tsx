// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useState } from 'react';
import { Archive } from 'lucide-react';
import { getParsedApiError } from '../../api/error';
import { researchPackExportApi } from '../../api/researchPackExport';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { RESEARCH_PACK_EXPORT_TEXT } from '../../locales/researchPackExport';
import { buildSettingsHref } from '../../routing/routes';
import { Button } from '../common/Button';
import { IconButton } from '../common/IconButton';
import { InlineAlert } from '../common/InlineAlert';

export interface ResearchPackExportControlsProps {
  recordId: number; variant?: 'toolbar' | 'section'; className?: string; disabled?: boolean;
}
type Feedback = { kind: 'disabled' | 'error' | 'truncated' | 'progress'; message: string } | null;

export const ResearchPackExportControls: React.FC<ResearchPackExportControlsProps> = ({
  recordId, variant = 'section', className, disabled = false,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const text = RESEARCH_PACK_EXPORT_TEXT[uiLanguage];
  const [exporting, setExporting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const settingsHref = buildSettingsHref({ section: 'agent_behavior', view: 'execution' });

  const handleExport = useCallback(async () => {
    setFeedback({ kind: 'progress', message: text.exportResearchPackBusy });
    setExporting(true);
    try {
      const result = await researchPackExportApi.download(recordId, 'zip', { language: uiLanguage === 'zh' ? 'zh' : 'en' });
      if (result.truncated) setFeedback({ kind: 'truncated', message: text.exportResearchPackTruncated });
      else if (result.progressHeader) {
        setFeedback({ kind: 'progress', message: `${text.exportResearchPackProgress}: ${result.progressHeader}` });
        window.setTimeout(() => setFeedback((c) => (c?.kind === 'progress' ? null : c)), 4000);
      } else setFeedback(null);
    } catch (error) {
      const parsed = getParsedApiError(error, uiLanguage);
      if (parsed.code === 'research_pack_export_disabled') {
        setFeedback({ kind: 'disabled', message: parsed.message || text.exportResearchPackDisabled });
      } else {
        setFeedback({ kind: 'error', message: parsed.message || text.exportResearchPackFailed });
      }
    } finally { setExporting(false); }
  }, [recordId, text, uiLanguage]);

  const controlsDisabled = disabled || exporting;
  const actions = variant === 'toolbar' ? (
    <IconButton type="button" variant="outline" size="default" onClick={() => { void handleExport(); }}
      disabled={controlsDisabled} aria-label={exporting ? text.exportResearchPackBusy : text.exportResearchPack}
      title={text.exportResearchPack} data-testid="research-pack-export"><Archive aria-hidden="true" /></IconButton>
  ) : (
    <Button type="button" variant="secondary" size="compact" onClick={() => { void handleExport(); }}
      disabled={controlsDisabled} data-testid="research-pack-export">
      <Archive className="h-3.5 w-3.5" aria-hidden="true" />
      {exporting ? text.exportResearchPackBusy : text.exportResearchPack}
    </Button>
  );

  return (
    <div className={className} data-testid="research-pack-export-controls">
      {variant === 'section' ? (
        <div className="space-y-2 rounded-lg border border-border bg-card p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{text.exportResearchPack}</p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">{text.exportResearchPackHint}</p>
            </div>
            {actions}
          </div>
        </div>
      ) : actions}
      {feedback?.kind === 'disabled' ? (
        <InlineAlert variant="warning" className="mt-3" data-testid="research-pack-export-disabled" message={(
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{feedback.message}</span>
            <a href={settingsHref} className="font-medium text-primary underline-offset-2 hover:underline"
              data-testid="research-pack-export-settings-link">{text.exportResearchPackDisabledLink}</a>
          </span>
        )} />
      ) : null}
      {feedback?.kind === 'error' ? <InlineAlert variant="danger" className="mt-3" message={feedback.message} data-testid="research-pack-export-error" /> : null}
      {feedback?.kind === 'truncated' ? <InlineAlert variant="warning" className="mt-3" message={feedback.message} data-testid="research-pack-export-truncated" /> : null}
      {feedback?.kind === 'progress' ? <InlineAlert variant="info" className="mt-3" message={feedback.message} data-testid="research-pack-export-progress" /> : null}
    </div>
  );
};
export default ResearchPackExportControls;
