// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, EmptyState } from '../common';
import { buildSettingsHref, SETTINGS_SECTION_IDS, SETTINGS_VIEW_IDS } from '../../routing/routes';

type AgentUnavailableEmptyStateProps = {
  title: string;
  description: string;
  actionLabel: string;
};

/** Informative empty state when Q&A Agent is unavailable (e.g. CLI-only). */
const AgentUnavailableEmptyState: React.FC<AgentUnavailableEmptyStateProps> = ({
  title,
  description,
  actionLabel,
}) => {
  const navigate = useNavigate();
  return (
    <EmptyState
      title={title}
      description={description}
      className="max-w-2xl"
      data-testid="chat-agent-unavailable"
      action={(
        <Button
          variant="secondary"
          size="comfortable"
          onClick={() => navigate(buildSettingsHref({
            section: SETTINGS_SECTION_IDS.aiModels,
            view: SETTINGS_VIEW_IDS.aiModels.connections,
          }))}
        >
          {actionLabel}
        </Button>
      )}
    />
  );
};

export { AgentUnavailableEmptyState };
