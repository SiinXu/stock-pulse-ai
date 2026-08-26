// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Inline plain-language help for risk levels, risk-gate verdicts, portfolio
 * health, and indicators (Issue #201).
 */
import { Info } from 'lucide-react';
import React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { getEducationHelpContent, loadEducationHelpContent } from '../../locales/educationHelp';
import type { EducationHelpKey } from '../../locales/educationHelpKeys';
import { IconButton } from '../common';

export interface HelpKeyButtonProps {
  helpKey: EducationHelpKey;
  /** Optional override; defaults to localized help title. */
  title?: string;
  className?: string;
  'data-testid'?: string;
}

/**
 * Three-part educational tooltip: what / why / what it means for you.
 * Falls back to summary + notes when usage/impact are absent.
 */
export const HelpKeyButton: React.FC<HelpKeyButtonProps> = ({
  helpKey,
  title,
  className,
  'data-testid': testId = 'help-key-button',
}) => {
  const { language, t } = useUiLanguage();
  const synchronousHelp = getEducationHelpContent(helpKey, language);
  const [loadedHelp, setLoadedHelp] = React.useState<{
    language: string;
    helpKey: EducationHelpKey;
    content: NonNullable<typeof synchronousHelp>;
  } | null>(null);

  React.useEffect(() => {
    if (synchronousHelp) return undefined;
    let active = true;
    void loadEducationHelpContent(helpKey, language).then((content) => {
      if (active) setLoadedHelp({ language, helpKey, content });
    });
    return () => {
      active = false;
    };
  }, [helpKey, language, synchronousHelp]);

  const help = synchronousHelp
    ?? (loadedHelp?.language === language && loadedHelp.helpKey === helpKey ? loadedHelp.content : null);
  if (!help) return null;

  const resolvedTitle = title?.trim() || help.title;
  const what = help.summary?.trim() || '';
  const why = help.usage?.trim() || '';
  const meansForYou = help.impact?.[0]?.trim() || help.notes?.[0]?.trim() || '';
  if (!what && !why && !meansForYou) {
    return null;
  }

  const ariaLabel = formatUiText(t('help.viewExplanation'), { title: resolvedTitle });

  const control = (
    <IconButton
      size="compact"
      variant="bare"
      aria-label={ariaLabel}
      data-testid={testId}
      data-help-key={helpKey}
      tooltip={(
        <span className="block space-y-2 py-1 text-left">
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
    >
      <Info aria-hidden="true" />
    </IconButton>
  );
  return className ? <span className={className}>{control}</span> : control;
};

export default HelpKeyButton;
