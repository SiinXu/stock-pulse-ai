// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useLocalOnlyModeStatus } from '../../hooks/useLocalOnlyModeStatus';
import { buildSettingsHref } from '../../routing/routes';
import { cn } from '../../utils/cn';
import { Tooltip } from '../common/Tooltip';

export const LOCAL_ONLY_MODE_FIELD_KEY = 'LOCAL_ONLY_MODE';

/** Settings → Auth & Security, focusing the Local Only Mode field. */
export function buildLocalOnlyModeSettingsHref(): string {
  const href = buildSettingsHref({
    section: 'system_security',
    view: 'security',
  });
  const separator = href.includes('?') ? '&' : '?';
  return `${href}${separator}field=${encodeURIComponent(LOCAL_ONLY_MODE_FIELD_KEY)}`;
}

export type LocalOnlyModeIndicatorProps = {
  className?: string;
};

export const LocalOnlyModeIndicator: React.FC<LocalOnlyModeIndicatorProps> = ({
  className,
}) => {
  const { t } = useUiLanguage();
  const { status } = useLocalOnlyModeStatus();

  if (status !== 'on') {
    return null;
  }

  const label = t('settings.outboundActivityModeOn');

  return (
    <Tooltip content={label} className={className}>
      <Link
        to={buildLocalOnlyModeSettingsHref()}
        aria-label={label}
        data-testid="shell-local-only-indicator"
        data-local-only-mode="on"
        className={cn(
          'inline-flex h-11 w-11 items-center justify-center rounded-lg border border-warning/20 bg-warning/10 text-warning transition-colors hover:bg-warning/15 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
        )}
      >
        <Shield className="h-4 w-4" aria-hidden="true" />
      </Link>
    </Tooltip>
  );
};
