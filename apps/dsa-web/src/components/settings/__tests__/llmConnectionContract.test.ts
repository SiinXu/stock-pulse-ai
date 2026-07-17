// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { LlmConnectionFieldSchema } from '../../../types/systemConfig';
import {
  buildConnectionContractValues,
  canonicalModelRoute,
  evaluateConnectionFieldStates,
  getProviderDisplayLabel,
  isConnectionModelDiscoveryEnabled,
  validateConnectionContractValues,
} from '../llmConnectionContract';

const contractCases = JSON.parse(fs.readFileSync(
  'src/components/settings/__tests__/fixtures/llmConnectionContractCases.json',
  'utf8',
)) as {
  cases: Array<{
    name: string;
    providerId: string;
    values: Record<string, string>;
    required: string[];
    visible: string[];
    missing: string[];
  }>;
};

const CONNECTION_FIELDS: LlmConnectionFieldSchema[] = [
  { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', requiredWhen: [{ key: 'enabled', operator: 'equals', value: 'true' }], visibleWhen: [{ key: 'protocol_visible', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', requiredWhen: [{ key: 'enabled', operator: 'equals', value: 'true' }, { key: 'base_url_required', operator: 'equals', value: 'true' }], visibleWhen: [{ key: 'base_url_visible', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: { requirement: 'optional', requiredWhen: [{ key: 'enabled', operator: 'equals', value: 'true' }, { key: 'api_key_required', operator: 'equals', value: 'true' }, { key: 'api_keys', operator: 'equals', value: '' }], visibleWhen: [{ key: 'api_key_visible', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: false, contract: { requirement: 'optional', visibleWhen: [{ key: 'api_key_visible', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: { requirement: 'optional', requiredWhen: [{ key: 'enabled', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'extra_headers', dataType: 'json', isSensitive: true, isRequired: false, contract: { requirement: 'optional', visibleWhen: [{ key: 'extra_headers_visible', operator: 'equals', value: 'true' }], requiresConnectionTest: true } },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
];

describe('canonicalModelRoute', () => {
  it('adds the connection protocol to bare model ids', () => {
    expect(canonicalModelRoute('openai', 'gpt-4o-mini')).toBe('openai/gpt-4o-mini');
  });

  it('keeps recognized LiteLLM route prefixes', () => {
    expect(canonicalModelRoute('openai', 'anthropic/claude-sonnet-4')).toBe('anthropic/claude-sonnet-4');
  });

  it('prefixes slash-containing provider model ids exactly like the backend', () => {
    expect(canonicalModelRoute('openai', 'deepseek-ai/DeepSeek-V3')).toBe(
      'openai/deepseek-ai/DeepSeek-V3',
    );
  });

  it('canonicalizes supported route aliases', () => {
    expect(canonicalModelRoute('openai', 'google/gemini-2.5-pro')).toBe('gemini/gemini-2.5-pro');
  });
});

describe('dynamic Connection field contract', () => {
  it('matches the same provider scenarios as the backend evaluator', () => {
    for (const fixture of contractCases.cases) {
      const states = evaluateConnectionFieldStates(fixture.values, CONNECTION_FIELDS);
      expect(
        Object.entries(states).filter(([, state]) => state.required).map(([key]) => key),
        fixture.name,
      ).toEqual(fixture.required);
      expect(
        Object.entries(states).filter(([, state]) => state.visible).map(([key]) => key),
        fixture.name,
      ).toEqual(fixture.visible);
      expect(validateConnectionContractValues(fixture.values, CONNECTION_FIELDS), fixture.name).toEqual(fixture.missing);
    }
  });

  it('preserves an empty display name from the shared backend fixture', () => {
    const fixture = contractCases.cases.find(
      (candidate) => candidate.name === 'enabled_connection_empty_display_name',
    );
    expect(fixture).toBeDefined();
    if (!fixture) return;

    const values = buildConnectionContractValues({
      connectionName: fixture.values.connection_name,
      displayName: fixture.values.display_name,
      providerId: fixture.providerId,
      protocol: fixture.values.protocol,
      baseUrl: fixture.values.base_url,
      apiKey: fixture.values.api_key,
      models: fixture.values.models,
      extraHeaders: fixture.values.extra_headers,
      enabled: fixture.values.enabled === 'true',
    });

    expect(values.display_name).toBe('');
    expect(validateConnectionContractValues(values, CONNECTION_FIELDS)).toEqual(fixture.missing);
  });

  it('keeps an unknown condition visible but read-only with a diagnostic', () => {
    const states = evaluateConnectionFieldStates(
      { provider_id: 'custom' },
      [{
        key: 'base_url',
        dataType: 'string',
        isSensitive: false,
        isRequired: false,
        contract: {
          requirement: 'optional',
          visibleWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'custom' }],
        },
      }],
    );
    expect(states.base_url).toMatchObject({ visible: true, enabled: false, unknownCondition: true });
  });

  it('builds schema context without legacy Catalog requirement flags', () => {
    const provider = {
      id: 'openai',
      label: 'OpenAI',
      protocol: 'openai',
      defaultBaseUrl: 'https://api.openai.com/v1',
      capabilities: [],
      requiresApiKey: false,
      requiresBaseUrl: true,
      supportsDiscovery: true,
      isLocal: false,
      isCustom: false,
    };
    const values = buildConnectionContractValues({
      connectionName: 'openai',
      displayName: 'OpenAI',
      providerId: 'openai',
      provider,
      protocol: 'openai',
      baseUrl: provider.defaultBaseUrl,
      apiKey: '',
      models: '',
      enabled: true,
    });

    expect(values.api_key_required).toBe('true');
    expect(values.base_url_required).toBe('false');
  });

  it('keeps Custom credentials visible when a localhost endpoint makes them optional', () => {
    const provider = {
      id: 'custom',
      label: 'Custom',
      protocol: 'openai',
      defaultBaseUrl: '',
      capabilities: [],
      requiresApiKey: true,
      requiresBaseUrl: true,
      supportsDiscovery: true,
      isLocal: false,
      isCustom: true,
    };
    const values = buildConnectionContractValues({
      connectionName: 'custom',
      displayName: 'Custom',
      providerId: 'custom',
      provider,
      protocol: 'openai',
      baseUrl: 'http://localhost:9000/v1',
      apiKey: '',
      models: 'local-model',
      enabled: true,
      emptyApiKeyHosts: ['localhost'],
    });

    expect(values.api_key_required).toBe('false');
    expect(values.api_key_visible).toBe('true');
  });

  it('gates discovery with schema-required test fields and unknown conditions', () => {
    const partialFields: LlmConnectionFieldSchema[] = [
      { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: true, contract: { requirement: 'required', requiresConnectionTest: true } },
      { key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: { requirement: 'optional', requiresConnectionTest: true } },
    ];
    expect(isConnectionModelDiscoveryEnabled({ api_key: '', models: '' }, partialFields)).toBe(false);
    expect(isConnectionModelDiscoveryEnabled({ api_key: 'key', models: '' }, partialFields)).toBe(false);

    const overrides = new Map(partialFields.map((field) => [field.key, field]));
    const fields = CONNECTION_FIELDS.map((field) => {
      const override = overrides.get(field.key);
      return override
        ? { ...override, contract: { ...override.contract } }
        : { ...field, contract: { ...field.contract } };
    });
    expect(isConnectionModelDiscoveryEnabled({
      connection_name: 'openai',
      provider_id: 'openai',
      api_key: 'key',
      models: '',
    }, fields)).toBe(true);

    const providerField = fields.find((field) => field.key === 'provider_id');
    expect(providerField).toBeDefined();
    providerField!.contract.enabledWhen = [
      { key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' },
    ];
    expect(isConnectionModelDiscoveryEnabled(
      { provider_id: 'openai', api_key: 'key', models: '' },
      fields,
    )).toBe(false);
  });

  it('selects bilingual labels and avoids a Chinese legacy label in English', () => {
    const provider = {
      id: 'openai',
      label: 'OpenAI 官方',
      labelZh: 'OpenAI 官方',
      labelEn: 'OpenAI Official',
      protocol: 'openai',
      defaultBaseUrl: 'https://api.openai.com/v1',
      capabilities: [],
      requiresApiKey: true,
      requiresBaseUrl: false,
      supportsDiscovery: true,
      isLocal: false,
      isCustom: false,
    };
    expect(getProviderDisplayLabel(provider, 'zh')).toBe('OpenAI 官方');
    expect(getProviderDisplayLabel(provider, 'en')).toBe('OpenAI Official');
    expect(getProviderDisplayLabel({ ...provider, labelEn: undefined }, 'en')).toBe('openai');
  });
});
