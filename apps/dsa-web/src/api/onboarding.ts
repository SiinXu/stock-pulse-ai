// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import apiClient from './index';
import { getParsedApiError } from './error';
import { toCamelCase } from './utils';
import type {
  DemoAnalysisPayload,
  FirstRunReadiness,
  OnboardingApplyResult,
  OnboardingPlan,
  OnboardingState,
  UserOnboardingProfile,
} from '../types/onboarding';

const BASE_PATH = '/api/v1/onboarding';

function toSnakeProfile(profile: UserOnboardingProfile): Record<string, unknown> {
  return {
    schema_version: profile.schemaVersion,
    experience_stage: profile.experienceStage,
    markets: profile.markets,
    goals: profile.goals,
    holdings: profile.holdings,
    interaction: profile.interaction,
    risk_tone: profile.riskTone,
    infrastructure: profile.infrastructure,
    report_language: profile.reportLanguage,
  };
}

export const onboardingApi = {
  async generatePlan(input: {
    profile: UserOnboardingProfile;
    modelAvailable?: boolean;
    preferLlm?: boolean;
  }): Promise<OnboardingPlan> {
    try {
      const response = await apiClient.post(`${BASE_PATH}/plan`, {
        profile: toSnakeProfile(input.profile),
        model_available: Boolean(input.modelAvailable),
        prefer_llm: Boolean(input.preferLlm),
      });
      return toCamelCase<OnboardingPlan>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async applyPlan(input: {
    profile: UserOnboardingProfile;
    configVersion: string;
    confirm?: boolean;
    modelAvailable?: boolean;
    preferLlm?: boolean;
  }): Promise<OnboardingApplyResult> {
    try {
      const response = await apiClient.post(`${BASE_PATH}/apply`, {
        profile: toSnakeProfile(input.profile),
        config_version: input.configVersion,
        confirm: input.confirm !== false,
        model_available: Boolean(input.modelAvailable),
        prefer_llm: Boolean(input.preferLlm),
      });
      return toCamelCase<OnboardingApplyResult>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getState(): Promise<OnboardingState> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/state`);
      return toCamelCase<OnboardingState>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async resetState(): Promise<{ success: boolean; reset: boolean; message: string }> {
    try {
      const response = await apiClient.delete(`${BASE_PATH}/state`);
      return toCamelCase(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getFirstRunReadiness(): Promise<FirstRunReadiness> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/first-run`);
      return toCamelCase<FirstRunReadiness>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },

  async getDemoAnalysis(reportLanguage = 'zh'): Promise<DemoAnalysisPayload> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/demo-analysis`, {
        params: { report_language: reportLanguage },
      });
      return toCamelCase<DemoAnalysisPayload>(response.data);
    } catch (error) {
      throw getParsedApiError(error);
    }
  },
};
