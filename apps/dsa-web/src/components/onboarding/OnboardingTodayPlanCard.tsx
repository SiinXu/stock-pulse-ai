// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useNavigate } from 'react-router-dom';
import type { OnboardingPlan } from '../../types/onboarding';
import type { UiTextKey } from '../../i18n/uiText';
import { Button, Section } from '../common';
import { clearCachedOnboardingPlan } from './onboardingDraftStorage';

export type OnboardingTodayPlanCardProps = {
  plan: OnboardingPlan;
  onDismiss?: () => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

export const OnboardingTodayPlanCard: React.FC<OnboardingTodayPlanCardProps> = ({
  plan,
  onDismiss,
  t,
}) => {
  const navigate = useNavigate();
  return (
    <Section
      title={t('onboarding.todayPlanCardTitle')}
      description={t('onboarding.todayPlanCardDescription', {
        stage: plan.featureStage,
        preset: plan.recommendedPresetName,
      })}
      level="interactive"
      padding="md"
      data-testid="onboarding-today-plan-card"
    >
      <ol className="list-decimal space-y-2 pl-5 text-sm text-secondary-text">
        {plan.todayPlan.map((item) => (
          <li key={item.id}>
            <span className="font-medium text-foreground">{item.title}</span>
            <span className="mt-0.5 block text-xs">{item.detail}</span>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="primary"
          size="default"
          onClick={() => navigate('/analysis')}
        >
          {t('onboarding.startAnalysis')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="default"
          onClick={() => navigate('/settings?section=overview&source=onboarding')}
        >
          {t('onboarding.openSettings')}
        </Button>
        {onDismiss ? (
          <Button
            type="button"
            variant="ghost"
            size="default"
            onClick={() => {
              clearCachedOnboardingPlan();
              onDismiss();
            }}
          >
            {t('onboarding.dismissPlan')}
          </Button>
        ) : null}
      </div>
      <p className="mt-3 text-xs text-muted-text">{plan.disclaimer}</p>
    </Section>
  );
};

export default OnboardingTodayPlanCard;
