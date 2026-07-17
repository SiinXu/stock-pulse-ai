import { CircleHelp, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import type React from 'react';
import type { SystemConfigFieldSchema } from '../../types/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { Modal, Tooltip } from '../common';

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

function hasItems<T>(items: T[] | undefined): items is T[] {
  return Boolean(items?.length);
}

function HelpSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  if (!children) {
    return null;
  }

  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-text">{title}</h3>
      {children}
    </section>
  );
}

function HelpList({ items }: { items?: string[] }) {
  if (!hasItems(items)) {
    return null;
  }

  return (
    <ul className="space-y-1.5 text-sm leading-6 text-secondary-text">
      {items.map((item) => (
        <li className="flex gap-2" key={item}>
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function CodeExamples({ examples }: { examples?: string[] }) {
  if (!hasItems(examples)) {
    return null;
  }

  return (
    <div className="space-y-2">
      {examples.map((example) => (
        <code
          className="block whitespace-pre-wrap break-words rounded-lg border border-border/70 bg-background/70 px-3 py-2 font-mono text-xs leading-5 text-foreground"
          key={example}
        >
          {example}
        </code>
      ))}
    </div>
  );
}

export const SettingsHelpButton: React.FC<SettingsHelpButtonProps> = ({
  fieldKey,
  title,
  schema,
  helpKey,
  examples: providedExamples,
  docs: providedDocs,
  description,
  rawValueExists,
}) => {
  const { language, t } = useUiLanguage();
  const help = getSettingsHelpContent(helpKey ?? schema?.helpKey, description, language);
  const defaultValue = schema?.defaultValue != null ? String(schema.defaultValue) : '';
  const hasDefault = defaultValue.length > 0;
  // Authoritative source of the saved value: explicit when the backend reports a
  // raw value exists; otherwise it falls back to the built-in default (if any).
  const valueSource: 'explicit' | 'default' | 'unset' | null =
    rawValueExists === undefined
      ? null
      : rawValueExists
        ? 'explicit'
        : hasDefault
          ? 'default'
          : 'unset';
  const sourceLabel =
    valueSource === 'explicit'
      ? t('settings.sourceExplicit')
      : valueSource === 'default'
        ? t('settings.sourceDefault')
        : valueSource === 'unset'
          ? t('settings.sourceUnset')
          : '';
  const [open, setOpen] = useState(false);
  const examples = providedExamples ?? help?.examples ?? schema?.examples ?? [];
  const docs = providedDocs?.length ? providedDocs : schema?.docs?.length ? schema.docs : help?.docs ?? [];
  const showFieldKey = help?.showFieldKey ?? true;
  const helpButtonLabel = formatUiText(SETTINGS_MISC_TEXT[language].helpLabel, { title });

  if (!help) {
    return null;
  }

  return (
    <>
      <Tooltip content={t('settings.helpTooltip')}>
        <span className="inline-flex">
          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-transparent text-muted-text transition-colors hover:border-[var(--settings-border)] hover:bg-[var(--settings-surface-hover)] hover:text-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/15"
            aria-label={helpButtonLabel}
            aria-expanded={open}
            aria-haspopup="dialog"
            onClick={() => setOpen(true)}
          >
            <CircleHelp aria-hidden="true" className="h-4 w-4" />
          </button>
        </span>
      </Tooltip>

      <Modal
        isOpen={open}
        onClose={() => setOpen(false)}
        title={help.title || title}
        description={help.summary}
        closeLabel={t('settings.helpClose')}
        className="max-w-2xl"
      >
        <div className="space-y-5">
          {showFieldKey ? (
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
              {fieldKey}
            </p>
          ) : null}
          <HelpSection title={t('settings.helpPurpose')}>
            {help.usage ? <p className="text-sm leading-6 text-secondary-text">{help.usage}</p> : null}
          </HelpSection>

          {valueSource ? (
            <HelpSection title={t('settings.helpCurrentSource')}>
              <p className="text-sm leading-6 text-secondary-text">
                {sourceLabel}
                {valueSource === 'default' && !schema?.isSensitive ? (
                  <>
                    {' '}
                    <span className="text-muted-text">{t('settings.sourceDefaultValueLabel')}: </span>
                    <code className="rounded bg-background/70 px-1.5 py-0.5 font-mono text-xs text-foreground">{defaultValue}</code>
                  </>
                ) : null}
              </p>
            </HelpSection>
          ) : null}

          <HelpSection title={t('settings.helpValueNotes')}>
            <HelpList items={help.valueNotes} />
          </HelpSection>

          {hasItems(examples) ? (
            <HelpSection title={t('settings.helpExamples')}>
              <CodeExamples examples={examples} />
            </HelpSection>
          ) : null}

          <HelpSection title={t('settings.helpImpact')}>
            <HelpList items={help.impact} />
          </HelpSection>

          <HelpSection title={t('settings.helpNotes')}>
            <HelpList items={help.notes} />
          </HelpSection>

          {hasItems(docs) ? (
            <HelpSection title={t('settings.helpRelatedDocs')}>
              <div className="flex flex-wrap gap-2">
                {docs.map((doc) => (
                  <a
                    className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-lg border border-border/70 bg-background/60 px-3 py-2 text-xs text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
                    href={doc.href}
                    key={`${doc.label}-${doc.href}`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <span>{doc.label}</span>
                    <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                  </a>
                ))}
              </div>
            </HelpSection>
          ) : null}
        </div>
      </Modal>
    </>
  );
};
