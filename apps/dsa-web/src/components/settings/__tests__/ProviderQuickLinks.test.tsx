import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { LlmProviderCatalogEntry } from '../../../types/systemConfig';
import { ProviderQuickLinks } from '../ProviderQuickLinks';

const provider: LlmProviderCatalogEntry = {
  id: 'example',
  label: 'Example',
  protocol: 'openai',
  defaultBaseUrl: 'https://api.example.com/v1',
  credentialUrl: 'https://console.example.com/keys',
  consoleUrl: 'https://console.example.com/',
  modelsUrl: 'https://docs.example.com/models',
  docsUrl: 'https://docs.example.com/',
  capabilities: [],
  requiresApiKey: true,
  requiresBaseUrl: false,
  supportsDiscovery: true,
  isLocal: false,
  isCustom: false,
};

describe('ProviderQuickLinks', () => {
  it('renders catalog credential links with safe external-link attributes', () => {
    render(
      <ProviderQuickLinks
        provider={provider}
        context="credentials"
        language="en"
        primaryLabel="Get API key"
        secondaryLabel="Console"
      />,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).not.toHaveAttribute('title');
      expect(link).toHaveAccessibleName(/opens in a new tab/);
      expect(link).toHaveAccessibleName(/console\.example\.com/);
      expect(link).toHaveClass('min-h-11', 'min-w-11');
    }
  });

  it('omits absent and duplicate catalog URLs', () => {
    const { rerender } = render(
      <ProviderQuickLinks
        provider={{ ...provider, modelsUrl: 'javascript:alert(1)', docsUrl: 'not a URL' }}
        context="models"
        language="en"
        primaryLabel="Models"
        secondaryLabel="Docs"
      />,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();

    rerender(
      <ProviderQuickLinks
        provider={{ ...provider, docsUrl: provider.modelsUrl }}
        context="models"
        language="en"
        primaryLabel="Models"
        secondaryLabel="Docs"
      />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('rejects plaintext HTTP catalog URLs', () => {
    render(
      <ProviderQuickLinks
        provider={{
          ...provider,
          modelsUrl: 'http://docs.example.com/models',
          docsUrl: 'https://docs.example.com/',
        }}
        context="models"
        language="en"
        primaryLabel="Models"
        secondaryLabel="Docs"
      />,
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://docs.example.com/');
  });

  it('rejects HTTPS catalog URLs containing credentials', () => {
    render(
      <ProviderQuickLinks
        provider={{
          ...provider,
          modelsUrl: 'https://user:secret@docs.example.com/models',
          docsUrl: undefined,
        }}
        context="models"
        language="en"
        primaryLabel="Models"
        secondaryLabel="Docs"
      />,
    );

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('normalizes catalog URLs before deduplicating them', () => {
    render(
      <ProviderQuickLinks
        provider={{
          ...provider,
          modelsUrl: 'HTTPS://DOCS.EXAMPLE.COM:443/models',
          docsUrl: 'https://docs.example.com/models',
        }}
        context="models"
        language="en"
        primaryLabel="Models"
        secondaryLabel="Docs"
      />,
    );

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://docs.example.com/models');
  });
});
