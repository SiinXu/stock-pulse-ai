import type { UiLanguage } from '../../i18n/uiText';
import { MODEL_ACCESS_TEXT } from '../../locales/settingsModelAccess';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';

export type ProviderCatalogResourceKind = 'credential' | 'console' | 'models' | 'docs';
export type ProviderCatalogResourceContext = 'credentials' | 'models' | 'all';

export interface ProviderCatalogResourceLink {
  kind: ProviderCatalogResourceKind;
  label: string;
  url: string;
  ariaLabel: string;
}

function safeExternalUrl(value: string | null | undefined): string | null {
  const raw = String(value ?? '').trim();
  if (!raw) {
    return null;
  }
  try {
    const parsed = new URL(raw);
    return parsed.protocol === 'https:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** Build safe, localized links exclusively from backend Catalog metadata. */
export function getProviderCatalogResourceLinks(
  provider: LlmProviderCatalogEntry,
  language: UiLanguage,
  context: ProviderCatalogResourceContext = 'all',
): ProviderCatalogResourceLink[] {
  const text = MODEL_ACCESS_TEXT[language];
  const candidates: Array<{
    kind: ProviderCatalogResourceKind;
    label: string;
    url: string | null | undefined;
    contexts: ProviderCatalogResourceContext[];
  }> = [
    {
      kind: 'credential',
      label: text.credentialLink,
      url: provider.credentialUrl,
      contexts: ['credentials', 'all'],
    },
    {
      kind: 'console',
      label: text.consoleLink,
      url: provider.consoleUrl,
      contexts: ['credentials', 'all'],
    },
    {
      kind: 'models',
      label: text.modelsLink,
      url: provider.modelsUrl,
      contexts: ['models', 'all'],
    },
    {
      kind: 'docs',
      label: text.docsLink,
      url: provider.docsUrl,
      contexts: ['models', 'all'],
    },
  ];

  const seen = new Set<string>();
  const links: ProviderCatalogResourceLink[] = [];
  for (const candidate of candidates) {
    if (!candidate.contexts.includes(context)) {
      continue;
    }
    const url = safeExternalUrl(candidate.url);
    if (!url || seen.has(url)) {
      continue;
    }
    seen.add(url);
    links.push({
      kind: candidate.kind,
      label: candidate.label,
      url,
      ariaLabel: `${candidate.label} - ${provider.label} (${text.opensExternal})`,
    });
  }
  return links;
}
