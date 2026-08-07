// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../common';
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
}) => (
  <EmptyState
    title={title}
    description={description}
    className="max-w-2xl"
    data-testid="chat-agent-unavailable"
    action={(
      <Link
        to={buildSettingsHref({
          section: SETTINGS_SECTION_IDS.aiModels,
          view: SETTINGS_VIEW_IDS.aiModels.taskRouting,
        })}
        className="inline-flex min-h-11 items-center justify-center rounded-lg border border-[var(--settings-border)] bg-[var(--nav-active-bg)] px-4 py-2 text-sm font-medium text-foreground"
      >
        {actionLabel}
      </Link>
    )}
  />
);

export { AgentUnavailableEmptyState };
