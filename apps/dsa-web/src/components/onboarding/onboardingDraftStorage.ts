// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  DEFAULT_ONBOARDING_PROFILE,
  ONBOARDING_DRAFT_STORAGE_KEY,
  ONBOARDING_PLAN_STORAGE_KEY,
  type OnboardingPlan,
  type UserOnboardingProfile,
} from '../../types/onboarding';

export type OnboardingWizardStep = 'intake' | 'plan' | 'done';

export interface OnboardingDraft {
  step: OnboardingWizardStep;
  profile: UserOnboardingProfile;
  updatedAt: string;
}

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function readOnboardingDraft(): OnboardingDraft | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(ONBOARDING_DRAFT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OnboardingDraft;
    if (!parsed || typeof parsed !== 'object') return null;
    return {
      step: parsed.step === 'plan' || parsed.step === 'done' ? parsed.step : 'intake',
      profile: {
        ...DEFAULT_ONBOARDING_PROFILE,
        ...(parsed.profile || {}),
        markets: Array.isArray(parsed.profile?.markets) && parsed.profile.markets.length > 0
          ? parsed.profile.markets
          : DEFAULT_ONBOARDING_PROFILE.markets,
      },
      updatedAt: parsed.updatedAt || new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function writeOnboardingDraft(draft: OnboardingDraft): void {
  if (!canUseStorage()) return;
  window.localStorage.setItem(
    ONBOARDING_DRAFT_STORAGE_KEY,
    JSON.stringify({ ...draft, updatedAt: new Date().toISOString() }),
  );
}

export function clearOnboardingDraft(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ONBOARDING_DRAFT_STORAGE_KEY);
}

export function readCachedOnboardingPlan(): OnboardingPlan | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(ONBOARDING_PLAN_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as OnboardingPlan;
  } catch {
    return null;
  }
}

export function writeCachedOnboardingPlan(plan: OnboardingPlan): void {
  if (!canUseStorage()) return;
  window.localStorage.setItem(ONBOARDING_PLAN_STORAGE_KEY, JSON.stringify(plan));
}

export function clearCachedOnboardingPlan(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ONBOARDING_PLAN_STORAGE_KEY);
}
