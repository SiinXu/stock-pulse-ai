// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Inline plain-language help entry that resolves copy through the shared
 * settings-help inventory (getSettingsHelpContent). Used outside Settings for
 * risk levels, risk-gate verdicts, portfolio health, and indicators (Issue #201).
 */
import { Info } from 'lucide-react';
import type React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { IconButton } from '../common';

export interface HelpKeyButtonProps {
  helpKey: string;
  /** Optional override; defaults to localized help title. */
  title?: string;
  className?: string;
  'data-testid'?: string;
}

/**
 * Three-part educational tooltip: what / why / what it means for you.
 * Falls back to summary + notes when usage/impact are absent (settings-style keys).
 */
export const HelpKeyButton: React.FC<HelpKeyButtonProps> = ({
  helpKey,
  title,
  className,
  'data-testid': testId = 'help-key-button',
}) => {
  const { language, t } = useUiLanguage();
  const help = getSettingsHelpContent(helpKey, undefined, language);
  if (!help) {
    return null;
  }

  const resolvedTitle = title?.trim() || help.title;
  const what = help.summary?.trim() || '';
  const why = help.usage?.trim() || '';
  const meansForYou = help.impact?.[0]?.trim() || help.notes?.[0]?.trim() || '';
  if (!what && !why && !meansForYou) {
    return null;
  }

  const ariaLabel = formatUiText(t('help.viewExplanation'), { title: resolvedTitle });

  return (
    <IconButton
      size="compact"
      variant="bare"
      className={className}
      aria-label={ariaLabel}
      data-testid={testId}
      data-help-key={helpKey}
      tooltip={(
        <span className="block w-64 space-y-2 py-1 text-left">
          {what ? (
            <span className="block">
              <span className="block font-medium text-foreground">{t('help.what')}</span>
              <span className="block text-secondary-text">{what}</span>
            </span>
          ) : null}
          {why && why !== what ? (
            <span className="block">
              <span className="block font-medium text-foreground">{t('help.why')}</span>
              <span className="block text-secondary-text">{why}</span>
            </span>
          ) : null}
          {meansForYou && meansForYou !== what && meansForYou !== why ? (
            <span className="block">
              <span className="block font-medium text-foreground">{t('help.meansForYou')}</span>
              <span className="block text-secondary-text">{meansForYou}</span>
            </span>
          ) : null}
        </span>
      )}
      tooltipContentClassName="max-w-[18rem]"
    >
      <Info aria-hidden="true" />
    </IconButton>
  );
};

export default HelpKeyButton;
