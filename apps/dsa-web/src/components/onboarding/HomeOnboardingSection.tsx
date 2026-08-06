// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import type { SetupStatusResponse } from '../../types/systemConfig';
import type { OnboardingPlan } from '../../types/onboarding';
import type { UiTextKey } from '../../i18n/uiText';
import { Button, IconButton, InlineAlert } from '../common';
import { buildSettingsHref } from '../../routing/routes';
import { AgentOnboardingWizard } from './AgentOnboardingWizard';
import { OnboardingTodayPlanCard } from './OnboardingTodayPlanCard';
import { readCachedOnboardingPlan } from './onboardingDraftStorage';

export type HomeOnboardingSectionProps = {
  setupStatus: SetupStatusResponse | null;
  setupMissingLabels: string;
  onboardingDismissed: boolean;
  onDismissOnboarding: () => void;
  onSetupRefresh: () => void;
  reportLanguage: string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

export const HomeOnboardingSection: React.FC<HomeOnboardingSectionProps> = ({
  setupStatus,
  setupMissingLabels,
  onboardingDismissed,
  onDismissOnboarding,
  onSetupRefresh,
  reportLanguage,
  t,
}) => {
  const navigate = useNavigate();
  const [agentOnboardingOpen, setAgentOnboardingOpen] = useState(false);
  const [todayPlan, setTodayPlan] = useState<OnboardingPlan | null>(() => readCachedOnboardingPlan());

  const modelAvailable = useMemo(() => {
    if (!setupStatus) return false;
    const primary = setupStatus.checks.find((check) => check.key === 'llm_primary');
    return primary ? primary.status !== 'needs_action' : Boolean(setupStatus.isComplete);
  }, [setupStatus]);

  const handleApplied = useCallback((plan: OnboardingPlan) => {
    setTodayPlan(plan);
    onSetupRefresh();
  }, [onSetupRefresh]);

  const showGap = Boolean(setupStatus && !setupStatus.isComplete && !onboardingDismissed);

  return (
    <>
      {showGap ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={t('home.setupIncomplete')}
          message={setupMissingLabels
            ? t('home.setupMissingWithLabels', { labels: setupMissingLabels })
            : t('home.setupMissingGeneric')}
          action={(
            <div className="flex flex-wrap items-center gap-1">
              <Button
                variant="primary"
                size="default"
                onClick={() => setAgentOnboardingOpen(true)}
              >
                {t('home.startAgentOnboarding')}
              </Button>
              <Button
                variant="secondary"
                size="default"
                onClick={() => navigate(buildSettingsHref({
                  section: 'overview',
                  view: 'readiness',
                  source: 'onboarding',
                }))}
              >
                {t('home.openSettingsManual')}
              </Button>
              <IconButton
                variant="ghost"
                size="default"
                aria-label={t('common.close')}
                onClick={onDismissOnboarding}
              >
                <X aria-hidden="true" />
              </IconButton>
            </div>
          )}
        />
      ) : null}

      {todayPlan ? (
        <OnboardingTodayPlanCard
          plan={todayPlan}
          t={t}
          onDismiss={() => setTodayPlan(null)}
        />
      ) : null}

      <AgentOnboardingWizard
        open={agentOnboardingOpen}
        onClose={() => setAgentOnboardingOpen(false)}
        onApplied={handleApplied}
        modelAvailable={modelAvailable}
        reportLanguage={reportLanguage}
        t={t}
      />
    </>
  );
};

export default HomeOnboardingSection;
