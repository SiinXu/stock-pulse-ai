// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { AgentOnboardingWizard } from './AgentOnboardingWizard';
import type { SetupStatusResponse } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';

export type SettingsAgentOnboardingHostProps = {
  open: boolean;
  onClose: () => void;
  onApplied: () => void;
  setupStatus: SetupStatusResponse | null;
  reportLanguage: string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

/** Thin Settings-page host so the page stays under the max-lines guard. */
export const SettingsAgentOnboardingHost: React.FC<SettingsAgentOnboardingHostProps> = ({
  open,
  onClose,
  onApplied,
  setupStatus,
  reportLanguage,
  t,
}) => (
  <AgentOnboardingWizard
    open={open}
    onClose={onClose}
    onApplied={onApplied}
    modelAvailable={Boolean(
      setupStatus?.checks?.some(
        (check) => check.key === 'llm_primary' && check.status !== 'needs_action',
      ),
    )}
    reportLanguage={reportLanguage}
    t={t}
  />
);

export default SettingsAgentOnboardingHost;
