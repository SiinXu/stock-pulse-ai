// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import AuthSettingsCard from './AuthSettingsCard';
import PluginsPanel from './plugins/PluginsPanel';
import SecurityAuditPanel from './SecurityAuditPanel';

type SystemSecurityPanelsProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

/**
 * System & Security → Auth & Security view surface.
 * Keeps SettingsPage under its max-lines budget while hosting additive panels.
 */
const SystemSecurityPanels: React.FC<SystemSecurityPanelsProps> = ({
  disabled = false,
  t,
  language,
}) => (
  <>
    <AuthSettingsCard />
    <SecurityAuditPanel disabled={disabled} t={t} language={language} />
    <PluginsPanel disabled={disabled} t={t} language={language} />
  </>
);

export default SystemSecurityPanels;
