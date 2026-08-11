// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { SetupStatusResponse } from '../../types/systemConfig';
import type { FirstRunReadiness, OnboardingPlan } from '../../types/onboarding';
import type { ReportLanguage } from '../../types/analysis';
import type { UiTextKey } from '../../i18n/uiText';
import { Button } from '../common';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
  buildSettingsHref,
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
} from '../../routing/routes';
import { AgentOnboardingWizard } from './AgentOnboardingWizard';
import { OnboardingTodayPlanCard } from './OnboardingTodayPlanCard';
import { readCachedOnboardingPlan } from './onboardingDraftStorage';
import { ZeroConfigFirstRunPanel } from './ZeroConfigFirstRunPanel';

export type HomeOnboardingSectionProps = {
  setupStatus: SetupStatusResponse | null;
  setupMissingLabels: string;
  onboardingDismissed: boolean;
  onDismissOnboarding: () => void;
  onSetupRefresh: () => void;
  reportLanguage: ReportLanguage;
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

  const handleFirstRunContinue = useCallback((readiness: FirstRunReadiness) => {
    if (readiness.primaryPath === 'local_ollama') {
      navigate(buildSettingsHref({
        section: SETTINGS_SECTION_IDS.aiModels,
        view: SETTINGS_VIEW_IDS.aiModels.localModels,
        source: 'onboarding',
      }));
      return;
    }
    navigate(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
    }));
  }, [navigate]);

  const showGap = Boolean(setupStatus && !setupStatus.isComplete && !onboardingDismissed);

  return (
    <>
      {showGap ? (
        <div className="space-y-2" data-testid="home-first-run-entry">
          <ZeroConfigFirstRunPanel
            reportLanguage={reportLanguage}
            onContinue={handleFirstRunContinue}
            onDismiss={onDismissOnboarding}
            t={t}
          />
          <p className="text-xs text-secondary-text">
            {setupMissingLabels
              ? t('home.setupMissingWithLabels', { labels: setupMissingLabels })
              : t('home.setupMissingGeneric')}
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="secondary"
              size="default"
              onClick={() => setAgentOnboardingOpen(true)}
            >
              {t('home.startAgentOnboarding')}
            </Button>
            <Button
              variant="ghost"
              size="default"
              onClick={() => navigate(buildSettingsHref({
                section: 'overview',
                view: 'readiness',
                source: 'onboarding',
              }))}
            >
              {t('home.openSettingsManual')}
            </Button>
          </div>
        </div>
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
