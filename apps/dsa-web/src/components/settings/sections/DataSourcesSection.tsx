// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import { SettingsPanelErrorBoundary } from '..';
import { IntelligenceSourcesPanel } from '../IntelligenceSourcesPanel';

export type DataSourcesSectionProps = {
  activeCategory: string;
  activeView: string;
  configVersion: string;
  settingsPanelDiagnosticHint: React.ReactNode;
  t: (...args: any[]) => string;
};

export const DataSourcesSection: React.FC<DataSourcesSectionProps> = (p) => (
  p.activeCategory === 'data_source' && p.activeView === 'intelligence' ? (
    <SettingsPanelErrorBoundary
      title={p.t('settings.pageTitle')}
      resetKey={`intelligence:${p.configVersion}`}
      diagnosticHint={p.settingsPanelDiagnosticHint}
    >
      <div className="mt-2">
        <IntelligenceSourcesPanel />
      </div>
    </SettingsPanelErrorBoundary>
  ) : null
);
