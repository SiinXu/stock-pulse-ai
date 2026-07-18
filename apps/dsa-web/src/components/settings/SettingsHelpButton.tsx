import { Info } from 'lucide-react';
import type React from 'react';
import type { SystemConfigFieldSchema } from '../../types/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { Tooltip } from '../common';

interface SettingsHelpButtonProps {
  fieldKey: string;
  title: string;
  schema?: SystemConfigFieldSchema;
  helpKey?: string;
  examples?: string[];
  docs?: SystemConfigFieldSchema['docs'];
  description?: string;
  /** Whether the saved config sets this key explicitly (vs. using the default). */
  rawValueExists?: boolean;
}

export const SettingsHelpButton: React.FC<SettingsHelpButtonProps> = ({
  title,
  schema,
  helpKey,
  description,
}) => {
  const { language, t } = useUiLanguage();
  const help = getSettingsHelpContent(helpKey ?? schema?.helpKey, description, language)
    ?? (description ? { title, summary: description } : null);
  const purpose = description ?? help?.summary ?? help?.usage ?? '';
  const recommendation = help?.notes?.[0] ?? help?.usage ?? help?.valueNotes?.[0] ?? '';
  const helpButtonLabel = formatUiText(SETTINGS_MISC_TEXT[language].helpLabel, { title });

  if (!help || (!purpose && !recommendation)) {
    return null;
  }

  return (
    <Tooltip
      content={(
        <span className="block w-64 space-y-2 py-1 text-left">
          {purpose ? (
            <span className="block">
              <span className="block font-medium text-foreground">{t('settings.helpPurpose')}</span>
              <span className="block text-secondary-text">{purpose}</span>
            </span>
          ) : null}
          {recommendation && recommendation !== purpose ? (
            <span className="block">
              <span className="block font-medium text-foreground">{t('settings.helpNotes')}</span>
              <span className="block text-secondary-text">{recommendation}</span>
            </span>
          ) : null}
        </span>
      )}
      contentClassName="max-w-[18rem]"
    >
      <button
        type="button"
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-text transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15"
        aria-label={helpButtonLabel}
      >
        <Info aria-hidden="true" className="h-4 w-4" />
      </button>
    </Tooltip>
  );
};
