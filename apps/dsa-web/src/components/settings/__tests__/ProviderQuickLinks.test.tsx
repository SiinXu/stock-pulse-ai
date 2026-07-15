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
});
