// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { onboardingApi } from '../../api/onboarding';
import { systemConfigApi } from '../../api/systemConfig';
import type { ParsedApiError } from '../../api/error';
import type {
  OnboardingGoal,
  OnboardingInfrastructure,
  OnboardingMarket,
  OnboardingPlan,
  OnboardingExperienceStage,
  OnboardingHoldings,
  OnboardingInteraction,
  OnboardingRiskTone,
  UserOnboardingProfile,
} from '../../types/onboarding';
import { DEFAULT_ONBOARDING_PROFILE } from '../../types/onboarding';
import type { UiTextKey } from '../../i18n/uiText';
import {
  Button,
  Checkbox,
  InlineAlert,
  Modal,
  Select,
} from '../common';
import {
  clearOnboardingDraft,
  readOnboardingDraft,
  writeCachedOnboardingPlan,
  writeOnboardingDraft,
  type OnboardingWizardStep,
} from './onboardingDraftStorage';

export type AgentOnboardingWizardProps = {
  open: boolean;
  onClose: () => void;
  /** Called after a successful apply so Home/Settings can refresh setup status. */
  onApplied?: (plan: OnboardingPlan) => void;
  /** Optional: whether a primary model is already usable (honest LLM gate). */
  modelAvailable?: boolean;
  reportLanguage?: string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function toggleListValue<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export const AgentOnboardingWizard: React.FC<AgentOnboardingWizardProps> = ({
  open,
  onClose,
  onApplied,
  modelAvailable = false,
  reportLanguage = 'zh',
  t,
}) => {
  const navigate = useNavigate();
  const [step, setStep] = useState<OnboardingWizardStep>('intake');
  const [profile, setProfile] = useState<UserOnboardingProfile>({
    ...DEFAULT_ONBOARDING_PROFILE,
    reportLanguage,
  });
  const [plan, setPlan] = useState<OnboardingPlan | null>(null);
  const [preferLlm, setPreferLlm] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<ParsedApiError | string | null>(null);
  const [appliedKeys, setAppliedKeys] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    const draft = readOnboardingDraft();
    if (draft) {
      setStep(draft.step === 'done' ? 'intake' : draft.step);
      setProfile({
        ...draft.profile,
        reportLanguage: draft.profile.reportLanguage || reportLanguage,
      });
    } else {
      setStep('intake');
      setProfile({ ...DEFAULT_ONBOARDING_PROFILE, reportLanguage });
    }
    setPlan(null);
    setError(null);
    setAppliedKeys([]);
  }, [open, reportLanguage]);

  useEffect(() => {
    if (!open) return;
    writeOnboardingDraft({ step, profile, updatedAt: new Date().toISOString() });
  }, [open, step, profile]);

  const errorMessage = useMemo(() => {
    if (!error) return null;
    if (typeof error === 'string') return error;
    return error.message || error.title || t('onboarding.errorGeneric');
  }, [error, t]);

  const handleGenerate = useCallback(async () => {
    if (profile.markets.length === 0) {
      setError(t('onboarding.marketsRequired'));
      return;
    }
    setIsGenerating(true);
    setError(null);
    try {
      const nextPlan = await onboardingApi.generatePlan({
        profile,
        modelAvailable,
        preferLlm,
      });
      setPlan(nextPlan);
      writeCachedOnboardingPlan(nextPlan);
      setStep('plan');
    } catch (err) {
      setError(err as ParsedApiError);
    } finally {
      setIsGenerating(false);
    }
  }, [modelAvailable, preferLlm, profile, t]);

  const handleApply = useCallback(async () => {
    if (!plan) return;
    setIsApplying(true);
    setError(null);
    try {
      const config = await systemConfigApi.getConfig(false);
      const result = await onboardingApi.applyPlan({
        profile,
        configVersion: config.configVersion,
        confirm: true,
        modelAvailable,
        preferLlm,
      });
      setPlan(result.plan);
      writeCachedOnboardingPlan(result.plan);
      setAppliedKeys(result.appliedKeys || []);
      setStep('done');
      clearOnboardingDraft();
      onApplied?.(result.plan);
    } catch (err) {
      setError(err as ParsedApiError);
    } finally {
      setIsApplying(false);
    }
  }, [modelAvailable, onApplied, plan, preferLlm, profile]);

  const handleSkip = useCallback(() => {
    clearOnboardingDraft();
    onClose();
  }, [onClose]);

  const handleFinish = useCallback(() => {
    clearOnboardingDraft();
    onClose();
  }, [onClose]);

  if (!open) return null;

  return (
    <Modal
      isOpen
      onClose={handleSkip}
      title={t('onboarding.title')}
      showHeaderDivider={false}
      size="default"
    >
      <div className="space-y-5" data-testid="agent-onboarding-wizard">
        <p className="text-xs text-muted-text">
          {step === 'intake'
            ? t('onboarding.stepIntake')
            : step === 'plan'
              ? t('onboarding.stepPlan')
              : t('onboarding.stepDone')}
        </p>
        <p className="text-sm text-secondary-text">{t('onboarding.subtitle')}</p>

        {errorMessage ? (
          <InlineAlert variant="danger" title={t('onboarding.errorTitle')} message={errorMessage} />
        ) : null}

        {step === 'intake' ? (
          <div className="space-y-4" data-testid="onboarding-intake">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="onboarding-stage">
                {t('onboarding.experienceStage')}
              </label>
              <Select
                id="onboarding-stage"
                value={profile.experienceStage}
                onChange={(value) => setProfile((prev) => ({
                  ...prev,
                  experienceStage: value as OnboardingExperienceStage,
                }))}
                options={[
                  { value: 'beginner', label: t('onboarding.stage.beginner') },
                  { value: 'report_reader', label: t('onboarding.stage.reportReader') },
                  { value: 'has_system', label: t('onboarding.stage.hasSystem') },
                ]}
              />
            </div>

            <fieldset>
              <legend className="mb-1 text-sm font-medium text-foreground">{t('onboarding.markets')}</legend>
              <div className="flex flex-wrap gap-3">
                {([
                  ['cn', 'onboarding.market.cn'],
                  ['hk', 'onboarding.market.hk'],
                  ['us', 'onboarding.market.us'],
                ] as const).map(([value, labelKey]) => (
                  <Checkbox
                    key={value}
                    checked={profile.markets.includes(value)}
                    onChange={() => setProfile((prev) => ({
                      ...prev,
                      markets: toggleListValue(prev.markets, value as OnboardingMarket),
                    }))}
                    label={t(labelKey)}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-1 text-sm font-medium text-foreground">{t('onboarding.goals')}</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {([
                  ['daily_push', 'onboarding.goal.dailyPush'],
                  ['pre_post_market', 'onboarding.goal.prePostMarket'],
                  ['holdings_risk', 'onboarding.goal.holdingsRisk'],
                  ['strategy_validation', 'onboarding.goal.strategyValidation'],
                ] as const).map(([value, labelKey]) => (
                  <Checkbox
                    key={value}
                    checked={profile.goals.includes(value)}
                    onChange={() => setProfile((prev) => ({
                      ...prev,
                      goals: toggleListValue(prev.goals, value as OnboardingGoal),
                    }))}
                    label={t(labelKey)}
                  />
                ))}
              </div>
            </fieldset>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="onboarding-holdings">
                  {t('onboarding.holdings')}
                </label>
                <Select
                  id="onboarding-holdings"
                  value={profile.holdings}
                  onChange={(value) => setProfile((prev) => ({
                    ...prev,
                    holdings: value as OnboardingHoldings,
                  }))}
                  options={[
                    { value: 'none', label: t('onboarding.holdings.none') },
                    { value: 'watchlist', label: t('onboarding.holdings.watchlist') },
                    { value: 'bookkeeping', label: t('onboarding.holdings.bookkeeping') },
                  ]}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="onboarding-interaction">
                  {t('onboarding.interaction')}
                </label>
                <Select
                  id="onboarding-interaction"
                  value={profile.interaction}
                  onChange={(value) => setProfile((prev) => ({
                    ...prev,
                    interaction: value as OnboardingInteraction,
                  }))}
                  options={[
                    { value: 'web', label: t('onboarding.interaction.web') },
                    { value: 'push', label: t('onboarding.interaction.push') },
                    { value: 'chat', label: t('onboarding.interaction.chat') },
                  ]}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="onboarding-risk">
                  {t('onboarding.riskTone')}
                </label>
                <Select
                  id="onboarding-risk"
                  value={profile.riskTone}
                  onChange={(value) => setProfile((prev) => ({
                    ...prev,
                    riskTone: value as OnboardingRiskTone,
                  }))}
                  options={[
                    { value: 'conservative', label: t('onboarding.risk.conservative') },
                    { value: 'balanced', label: t('onboarding.risk.balanced') },
                    { value: 'assertive', label: t('onboarding.risk.assertive') },
                  ]}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="onboarding-infra">
                  {t('onboarding.infrastructure')}
                </label>
                <Select
                  id="onboarding-infra"
                  value={profile.infrastructure}
                  onChange={(value) => setProfile((prev) => ({
                    ...prev,
                    infrastructure: value as OnboardingInfrastructure,
                  }))}
                  options={[
                    { value: 'cloud_key', label: t('onboarding.infra.cloudKey') },
                    { value: 'local_models', label: t('onboarding.infra.localModels') },
                    { value: 'free_only', label: t('onboarding.infra.freeOnly') },
                  ]}
                />
              </div>
            </div>

            <Checkbox
              checked={preferLlm}
              onChange={(event) => setPreferLlm(event.target.checked)}
              label={
                modelAvailable
                  ? t('onboarding.preferLlmAvailable')
                  : t('onboarding.preferLlmUnavailable')
              }
            />
            {!modelAvailable ? (
              <InlineAlert
                variant="info"
                title={t('onboarding.rulesOnlyTitle')}
                message={t('onboarding.rulesOnlyMessage')}
              />
            ) : null}
          </div>
        ) : null}

        {step === 'plan' && plan ? (
          <div className="space-y-4" data-testid="onboarding-plan-preview">
            <InlineAlert
              variant="info"
              title={t('onboarding.engineRules', { engine: plan.engine })}
              message={plan.llmNote}
            />
            <div className="rounded-lg border border-border bg-[var(--settings-surface)] p-3 text-sm">
              <p className="font-medium text-foreground">
                {t('onboarding.recommendedPreset')}: {plan.recommendedPresetName}
              </p>
              <p className="mt-1 text-secondary-text">
                {t('onboarding.featureStage')}: {plan.featureStage} · {plan.featurePath?.label}
              </p>
            </div>

            <section>
              <h3 className="mb-2 text-sm font-semibold text-foreground">{t('onboarding.configChanges')}</h3>
              {plan.configItems.length === 0 ? (
                <p className="text-sm text-secondary-text">{t('onboarding.noConfigChanges')}</p>
              ) : (
                <ul className="max-h-40 space-y-1 overflow-auto text-xs" data-testid="onboarding-config-changes">
                  {plan.configItems.map((item) => (
                    <li key={item.key} className="flex justify-between gap-2 border-b border-border/50 py-1">
                      <span className="font-mono text-foreground">{item.key}</span>
                      <span className="truncate text-secondary-text">{item.value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-sm font-semibold text-foreground">{t('onboarding.todos')}</h3>
              <ul className="space-y-2 text-sm">
                {plan.todos.map((todo) => (
                  <li key={todo.id} className="rounded-md border border-border/70 px-3 py-2">
                    <p className="font-medium text-foreground">{todo.title}</p>
                    <p className="mt-0.5 text-xs text-secondary-text">{todo.description}</p>
                    {todo.href ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="compact"
                        className="mt-1"
                        onClick={() => navigate(todo.href || '/settings')}
                      >
                        {t('onboarding.openLink')}
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h3 className="mb-2 text-sm font-semibold text-foreground">{t('onboarding.todayPlan')}</h3>
              <ol className="list-decimal space-y-1 pl-5 text-sm text-secondary-text">
                {plan.todayPlan.map((item) => (
                  <li key={item.id}>
                    <span className="font-medium text-foreground">{item.title}</span>
                    {' — '}
                    {item.detail}
                  </li>
                ))}
              </ol>
            </section>

            <p className="text-xs text-muted-text" data-testid="onboarding-disclaimer">
              {plan.disclaimer || t('onboarding.disclaimer')}
            </p>
          </div>
        ) : null}

        {step === 'done' && plan ? (
          <div className="space-y-3" data-testid="onboarding-done">
            <InlineAlert
              variant="success"
              title={t('onboarding.appliedTitle')}
              message={
                appliedKeys.length > 0
                  ? t('onboarding.appliedMessage', { count: appliedKeys.length })
                  : t('onboarding.appliedNoChanges')
              }
            />
            {appliedKeys.length > 0 ? (
              <p className="text-xs font-mono text-secondary-text">{appliedKeys.join(', ')}</p>
            ) : null}
            <div className="rounded-lg border border-border p-3 text-sm">
              <p className="font-medium text-foreground">{t('onboarding.todayPlan')}</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-secondary-text">
                {plan.todayPlan.map((item) => (
                  <li key={item.id}>{item.title}</li>
                ))}
              </ol>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="ghost" size="default" onClick={handleSkip}>
            {t('onboarding.skip')}
          </Button>
          {step === 'intake' ? (
            <Button
              type="button"
              variant="primary"
              size="default"
              isLoading={isGenerating}
              onClick={() => void handleGenerate()}
            >
              {t('onboarding.generatePlan')}
            </Button>
          ) : null}
          {step === 'plan' ? (
            <>
              <Button type="button" variant="secondary" size="default" onClick={() => setStep('intake')}>
                {t('onboarding.back')}
              </Button>
              <Button
                type="button"
                variant="primary"
                size="default"
                isLoading={isApplying}
                onClick={() => void handleApply()}
              >
                {t('onboarding.applyPlan')}
              </Button>
            </>
          ) : null}
          {step === 'done' ? (
            <>
              <Button
                type="button"
                variant="secondary"
                size="default"
                onClick={() => navigate('/settings?section=overview&source=onboarding')}
              >
                {t('onboarding.openSettings')}
              </Button>
              <Button type="button" variant="primary" size="default" onClick={handleFinish}>
                {t('onboarding.done')}
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </Modal>
  );
};

export default AgentOnboardingWizard;
