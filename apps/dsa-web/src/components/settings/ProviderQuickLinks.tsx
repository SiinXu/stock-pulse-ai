import { ExternalLink } from 'lucide-react';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';
import type { UiLanguage } from '../../i18n/uiText';
import { PROVIDER_QUICK_LINKS_TEXT } from './providerQuickLinksText';

interface ProviderQuickLinksProps {
  provider?: LlmProviderCatalogEntry;
  context: 'credentials' | 'models';
  language: UiLanguage;
  primaryLabel: string;
  secondaryLabel: string;
}

/** Render only backend-catalog links; provider IDs never select links in Web code. */
export function ProviderQuickLinks({
  provider,
  context,
  language,
  primaryLabel,
  secondaryLabel,
}: ProviderQuickLinksProps) {
  const text = PROVIDER_QUICK_LINKS_TEXT[language];
  const candidates = context === 'credentials'
    ? [
        { href: provider?.credentialUrl, label: primaryLabel },
        { href: provider?.consoleUrl, label: secondaryLabel },
      ]
    : [
        { href: provider?.modelsUrl, label: primaryLabel },
        { href: provider?.docsUrl, label: secondaryLabel },
      ];
  const seen = new Set<string>();
  const links = candidates.flatMap((candidate) => {
    const href = candidate.href?.trim();
    if (!href) {
      return [];
    }
    let parsed: URL;
    try {
      parsed = new URL(href);
    } catch {
      return [];
    }
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password) {
      return [];
    }
    const normalizedHref = parsed.href;
    if (seen.has(normalizedHref)) {
      return [];
    }
    seen.add(normalizedHref);
    return [{ href: normalizedHref, label: candidate.label, hostname: parsed.hostname }];
  });

  if (links.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-text">
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${link.label} (${text.opensInNewTab}; ${link.hostname})`}
          className="settings-accent-text inline-flex min-h-11 min-w-11 items-center justify-center gap-1 underline-offset-2 hover:underline"
        >
          <span>{link.label}</span>
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
      ))}
    </div>
  );
}
