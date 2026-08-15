// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { BarChart3, Monitor, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button, EmptyState } from '../common';
import {
  buildAnalysisWorkbenchHref,
  buildSettingsHref,
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
} from '../../routing/routes';

type AgentUnavailableEmptyStateProps = {
  title: string;
  description: string;
  actionLabel: string;
  localActionLabel: string;
  analysisActionLabel: string;
};

/** Informative empty state when Q&A Agent is unavailable (e.g. CLI-only). */
const AgentUnavailableEmptyState: React.FC<AgentUnavailableEmptyStateProps> = ({
  title,
  description,
  actionLabel,
  localActionLabel,
  analysisActionLabel,
}) => {
  const navigate = useNavigate();
  const modelSourcesHref = buildSettingsHref({
    section: SETTINGS_SECTION_IDS.aiModels,
    view: SETTINGS_VIEW_IDS.aiModels.connections,
  });

  return (
    <EmptyState
      title={title}
      description={description}
      className="max-w-2xl"
      data-testid="chat-agent-unavailable"
      action={(
        <div className="flex max-w-xl flex-wrap justify-center gap-x-2 gap-y-4">
          <Button
            variant="primary"
            size="comfortable"
            onClick={() => navigate(modelSourcesHref)}
          >
            <Settings className="h-4 w-4" aria-hidden="true" />
            {actionLabel}
          </Button>
          <Button
            variant="secondary"
            size="comfortable"
            onClick={() => navigate(modelSourcesHref)}
          >
            <Monitor className="h-4 w-4" aria-hidden="true" />
            {localActionLabel}
          </Button>
          <Button
            variant="ghost"
            size="comfortable"
            onClick={() => navigate(buildAnalysisWorkbenchHref())}
          >
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            {analysisActionLabel}
          </Button>
        </div>
      )}
    />
  );
};

export { AgentUnavailableEmptyState };
