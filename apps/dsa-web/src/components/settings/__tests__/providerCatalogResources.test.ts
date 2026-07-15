import { describe, expect, it } from 'vitest';
import type { LlmProviderCatalogEntry } from '../../../types/systemConfig';
import { getProviderCatalogResourceLinks } from '../providerCatalogResources';

function provider(overrides: Partial<LlmProviderCatalogEntry> = {}): LlmProviderCatalogEntry {
  return {
    id: 'arbitrary-provider',
    label: 'Arbitrary Provider',
    protocol: 'openai',
    defaultBaseUrl: 'https://api.example.test/v1',
    capabilities: [],
    requiresApiKey: true,
    requiresBaseUrl: false,
    supportsDiscovery: false,
    isLocal: false,
    isCustom: false,
    ...overrides,
  };
}

describe('getProviderCatalogResourceLinks', () => {
  it('uses only Catalog metadata and localizes link labels', () => {
    const entry = provider({
      credentialUrl: 'https://console.example.test/keys',
      consoleUrl: 'https://console.example.test/',
      modelsUrl: 'https://docs.example.test/models',
      docsUrl: 'https://docs.example.test/api',
    });

    expect(getProviderCatalogResourceLinks(entry, 'zh', 'credentials')).toEqual([
      {
        kind: 'credential',
        label: '获取 API 密钥',
        url: 'https://console.example.test/keys',
        ariaLabel: '获取 API 密钥 - Arbitrary Provider (将在新标签页打开)',
      },
      {
        kind: 'console',
        label: '服务商控制台',
        url: 'https://console.example.test/',
        ariaLabel: '服务商控制台 - Arbitrary Provider (将在新标签页打开)',
      },
    ]);
    expect(getProviderCatalogResourceLinks(entry, 'en', 'models').map((link) => link.label)).toEqual([
      'Model list',
      'Developer docs',
    ]);
  });

  it('omits missing, duplicate, and unsafe links', () => {
    const entry = provider({
      credentialUrl: 'https://console.example.test/',
      consoleUrl: 'https://console.example.test/',
      modelsUrl: 'javascript:alert(1)',
      docsUrl: 'http://insecure.example.test/',
    });

    expect(getProviderCatalogResourceLinks(entry, 'en')).toEqual([
      expect.objectContaining({ kind: 'credential', url: 'https://console.example.test/' }),
    ]);
  });

  it('returns no fallback business links when Catalog metadata is absent', () => {
    expect(getProviderCatalogResourceLinks(provider(), 'en')).toEqual([]);
  });
});
