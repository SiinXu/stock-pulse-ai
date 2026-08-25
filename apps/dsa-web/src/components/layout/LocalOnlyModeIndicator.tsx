// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useLocalOnlyModeStatus } from '../../hooks/useLocalOnlyModeStatus';
import { cn } from '../../utils/cn';
import { Tooltip } from '../common/Tooltip';
import { buildLocalOnlyModeSettingsHref } from './localOnlyMode';

export type LocalOnlyModeIndicatorProps = {
  className?: string;
  /** Playground preview only. Production Shell omits this and uses the live endpoint. */
  previewStatus?: 'unknown' | 'off' | 'on';
};

export const LocalOnlyModeIndicator: React.FC<LocalOnlyModeIndicatorProps> = ({
  className,
  previewStatus,
}) => {
  const { t } = useUiLanguage();
  const fetched = useLocalOnlyModeStatus();
  const status = previewStatus ?? fetched.status;

  if (status !== 'on') {
    return null;
  }

  const hint = t('layout.localOnlyModeOpenSettings');

  return (
    <Tooltip content={hint} className={className}>
      <Link
        to={buildLocalOnlyModeSettingsHref()}
        aria-label={hint}
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
