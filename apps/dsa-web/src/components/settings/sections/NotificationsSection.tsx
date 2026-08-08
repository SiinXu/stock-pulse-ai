// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import { NotificationTestPanel, SettingsPanelErrorBoundary } from '..';

export type NotificationsSectionProps = {
  activeCategory: string;
  activeSubCategory: string | null;
  configVersion: string;
  settingsPanelDiagnosticHint: React.ReactNode;
  rawActiveItems: Array<{ key: string; value: unknown }>;
  maskToken: string;
  isSaving: boolean;
  isLoading: boolean;
  t: (...args: any[]) => string;
};

export const NotificationsSection: React.FC<NotificationsSectionProps> = (p) => (
  p.activeCategory === 'notification' && p.activeSubCategory === 'channels' ? (
    <SettingsPanelErrorBoundary
      title={p.t('settings.notificationTest')}
      resetKey={`notification-test:${p.configVersion}`}
      diagnosticHint={p.settingsPanelDiagnosticHint}
    >
      <NotificationTestPanel
        items={p.rawActiveItems.map((item) => ({ key: item.key, value: String(item.value ?? '') }))}
        maskToken={p.maskToken}
        disabled={p.isSaving || p.isLoading}
      />
    </SettingsPanelErrorBoundary>
  ) : null
);
