// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import type { UiLanguage } from '../../../i18n/uiLanguages';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { AuthSettingsCard, ChangePasswordCard } from '..';
import SystemAboutCard from '../SystemAboutCard';
import SchedulerSettingsCard from '../SchedulerSettingsCard';
import ScheduledTasksPanel from '../ScheduledTasksPanel';
import SecurityAuditPanel from '../SecurityAuditPanel';
import OutboundActivityPanel from '../OutboundActivityPanel';
import SignalScorecardPanel from '../SignalScorecardPanel';

export type SystemSecuritySectionProps = {
  activeCategory: string;
  activeView: string;
  passwordChangeable: boolean;
  rawActiveItems: SystemConfigItem[];
  isSaving: boolean;
  isLoading: boolean;
  issueByKey: Record<string, any>;
  schedulerStatusRefreshToken: number;
  handleSchedulerRuntimeStateChange: (...args: any[]) => void;
  setDraftValue: (key: string, value: string) => void;
  allValuesByKey: Record<string, string>;
  t: (...args: any[]) => string;
  language: UiLanguage;
};

/** System & Security section specialized panels (not the generic field panel). */
export const SystemSecuritySection: React.FC<SystemSecuritySectionProps> = ({
  activeCategory,
  activeView,
  passwordChangeable,
  rawActiveItems,
  isSaving,
  isLoading,
  issueByKey,
  schedulerStatusRefreshToken,
  handleSchedulerRuntimeStateChange,
  setDraftValue,
  allValuesByKey,
  t,
  language,
}) => (
  <>
    {activeCategory === 'system' && activeView === 'security' ? (
      <>
        <AuthSettingsCard />
        <OutboundActivityPanel disabled={isSaving || isLoading} t={t} language={language} />
        <SecurityAuditPanel disabled={isSaving || isLoading} t={t} language={language} />
      </>
    ) : null}
    {activeCategory === 'system' && activeView === 'runtime' ? (
      <>
        <SchedulerSettingsCard
          items={rawActiveItems}
          disabled={isSaving || isLoading}
          issueByKey={issueByKey}
          statusRefreshToken={schedulerStatusRefreshToken}
          onSchedulerStateChange={handleSchedulerRuntimeStateChange}
          onChange={setDraftValue}
          t={t}
          language={language}
        />
        <ScheduledTasksPanel disabled={isSaving || isLoading} t={t} language={language} />
      </>
    ) : null}
    {activeCategory === 'system' && activeView === 'general' ? (
      <SignalScorecardPanel
        publicEnabled={['1', 'true', 'yes', 'on'].includes(
          String(allValuesByKey.SIGNAL_SCORECARD_PUBLIC_ENABLED ?? '').trim().toLowerCase(),
        )}
        minSamples={(() => {
          const raw = String(allValuesByKey.SIGNAL_SCORECARD_MIN_SAMPLES ?? '').trim();
          if (!raw) return 10;
          const parsed = Number.parseInt(raw, 10);
          return Number.isFinite(parsed) ? parsed : 10;
        })()}
        disabled={isSaving || isLoading}
        t={t}
        language={language}
      />
    ) : null}
    {activeCategory === 'system' && activeView === 'about' ? (
      <SystemAboutCard />
    ) : null}
    {activeCategory === 'system' && activeView === 'security' && passwordChangeable ? (
      <ChangePasswordCard />
    ) : null}
  </>
);
