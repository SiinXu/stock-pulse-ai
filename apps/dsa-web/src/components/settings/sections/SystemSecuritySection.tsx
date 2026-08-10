// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { AuthSettingsCard, ChangePasswordCard, LoadedExtensionsPanel } from '..';
import OutboundActivityPanel from '../OutboundActivityPanel';
import SchedulerSettingsCard from '../SchedulerSettingsCard';
import ScheduledTasksPanel from '../ScheduledTasksPanel';
import SecurityAuditPanel from '../SecurityAuditPanel';
import SignalScorecardPanel from '../SignalScorecardPanel';
import SystemAboutCard from '../SystemAboutCard';

type SchedulerProps = React.ComponentProps<typeof SchedulerSettingsCard>;
type ExtensionProps = React.ComponentProps<typeof LoadedExtensionsPanel>;

export type SystemSecuritySectionProps = {
  activeCategory: string;
  activeView: string;
  passwordChangeable: boolean;
  items: SchedulerProps['items'];
  disabled: boolean;
  issueByKey: SchedulerProps['issueByKey'];
  schedulerStatusRefreshToken: number;
  onSchedulerStateChange: SchedulerProps['onSchedulerStateChange'];
  onChange: SchedulerProps['onChange'];
  allValuesByKey: Readonly<Record<string, string>>;
  t: ExtensionProps['t'];
  language: ExtensionProps['language'];
};

function parseMinimumSamples(value: string | undefined): number {
  const raw = String(value ?? '').trim();
  if (!raw) return 10;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : 10;
}

export const SystemSecuritySection: React.FC<SystemSecuritySectionProps> = (props) => {
  if (props.activeCategory !== 'system') return null;

  if (props.activeView === 'security') {
    return (
      <>
        <AuthSettingsCard />
        <OutboundActivityPanel disabled={props.disabled} t={props.t} language={props.language} />
        <SecurityAuditPanel disabled={props.disabled} t={props.t} language={props.language} />
        {props.passwordChangeable ? <ChangePasswordCard /> : null}
      </>
    );
  }

  if (props.activeView === 'runtime') {
    return (
      <>
        <SchedulerSettingsCard
          items={props.items}
          disabled={props.disabled}
          issueByKey={props.issueByKey}
          statusRefreshToken={props.schedulerStatusRefreshToken}
          onSchedulerStateChange={props.onSchedulerStateChange}
          onChange={props.onChange}
          t={props.t}
          language={props.language}
        />
        <ScheduledTasksPanel disabled={props.disabled} t={props.t} language={props.language} />
      </>
    );
  }

  if (props.activeView === 'general') {
    return (
      <SignalScorecardPanel
        publicEnabled={['1', 'true', 'yes', 'on'].includes(
          String(props.allValuesByKey.SIGNAL_SCORECARD_PUBLIC_ENABLED ?? '').trim().toLowerCase(),
        )}
        minSamples={parseMinimumSamples(props.allValuesByKey.SIGNAL_SCORECARD_MIN_SAMPLES)}
        disabled={props.disabled}
        t={props.t}
        language={props.language}
      />
    );
  }

  if (props.activeView === 'about') return <SystemAboutCard />;
  if (props.activeView === 'extensions') {
    return <LoadedExtensionsPanel disabled={props.disabled} t={props.t} language={props.language} />;
  }
  return null;
};
