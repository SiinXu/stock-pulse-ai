// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { LlmConnectionFieldSchema, LlmProviderCatalogEntry } from '../../../types/systemConfig';
import {
  CHANNEL_VALIDATION_ISSUE_CODES,
  CONNECTION_SCHEMA_UNAVAILABLE_ISSUE,
  CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE,
  findChannelValidationIssue,
  getChannelCompletenessIssues,
  getChannelDisplayNameIssues,
  getChannelNameConflictIssue,
  getChannelNameIssues,
  getChannelSaveIssues,
  type ChannelConfig,
} from '../llmChannelEditorModel';

const PRODUCTION_CALLERS = [
  'src/components/settings/LLMChannelEditor.tsx',
  'src/components/settings/LLMConnectionCard.tsx',
  'src/components/settings/LLMConnectionModal.tsx',
] as const;

function channel(overrides: Partial<ChannelConfig> = {}): ChannelConfig {
  return {
    id: 'test:openai',
    name: 'openai',
    displayName: 'OpenAI',
    displayNameValuePresent: true,
    providerId: 'openai',
    providerIdExplicit: true,
    protocol: 'openai',
    protocolValuePresent: true,
    baseUrl: 'https://api.openai.com/v1',
    apiKey: 'sk-test',
    credentialField: 'api_key',
    models: 'gpt-4.1',
    extraHeaders: '',
    enabled: true,
    enabledValuePresent: true,
    ...overrides,
  };
}

function provider(
  overrides: Partial<LlmProviderCatalogEntry> & Pick<LlmProviderCatalogEntry, 'id' | 'label' | 'protocol'>,
): LlmProviderCatalogEntry {
  return {
    defaultBaseUrl: '',
    capabilities: [],
    requiresApiKey: true,
    requiresBaseUrl: false,
    supportsDiscovery: false,
    isLocal: false,
    isCustom: false,
    ...overrides,
  };
}

const PROVIDERS: LlmProviderCatalogEntry[] = [
  provider({
    id: 'openai',
    label: 'OpenAI',
    protocol: 'openai',
    defaultBaseUrl: 'https://api.openai.com/v1',
  }),
  provider({
    id: 'ollama',
    label: 'Ollama',
    protocol: 'ollama',
    defaultBaseUrl: 'http://127.0.0.1:11434',
    requiresApiKey: false,
    isLocal: true,
  }),
  provider({
    id: 'custom',
    label: 'Custom',
    protocol: 'openai',
    isCustom: true,
    requiresBaseUrl: true,
  }),
];

const CORE_FIELDS: LlmConnectionFieldSchema[] = [
  { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: true, contract: { requirement: 'required' } },
  { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: false, contract: { requirement: 'optional' } },
  { key: 'models', dataType: 'array', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'extra_headers', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
];

function withCoreFields(overrides: LlmConnectionFieldSchema[] = []): LlmConnectionFieldSchema[] {
  const byKey = new Map([...CORE_FIELDS, ...overrides].map((entry) => [entry.key, entry]));
  return Array.from(byKey.values());
}

describe('LLM connection validation contract', () => {
  it('returns structured codes instead of locale copy for name issues', () => {
    expect(getChannelNameIssues(channel({ name: '' }))).toEqual([
      { code: CHANNEL_VALIDATION_ISSUE_CODES.nameRequired, field: 'connection_name' },
    ]);
    expect(getChannelNameIssues(channel({ name: 'OpenAI' }))).toEqual([
      { code: CHANNEL_VALIDATION_ISSUE_CODES.nameInvalid, field: 'connection_name' },
    ]);
    expect(getChannelNameIssues(channel({ name: 'openai_2' }))).toEqual([]);
    expect(getChannelNameConflictIssue(channel({ name: 'openai' }), ['openai'])).toEqual({
      code: CHANNEL_VALIDATION_ISSUE_CODES.nameConflict,
      field: 'connection_name',
    });
  });

  it('preserves field targeting for schema-backed completeness issues', () => {
    const issues = getChannelCompletenessIssues(
      channel({
        displayName: '',
        displayNameValuePresent: false,
        apiKey: '',
        baseUrl: '',
        models: '',
        extraHeaders: '',
      }),
      PROVIDERS,
      [],
      CORE_FIELDS,
    );
    expect(findChannelValidationIssue(issues, { fields: ['display_name'] })?.code)
      .toBe(CHANNEL_VALIDATION_ISSUE_CODES.nameRequired);
    expect(findChannelValidationIssue(issues, { fields: ['api_key', 'api_keys'] })?.code)
      .toBe(CHANNEL_VALIDATION_ISSUE_CODES.missingApiKey);
    expect(findChannelValidationIssue(issues, { fields: ['base_url'] })?.code)
      .toBe(CHANNEL_VALIDATION_ISSUE_CODES.missingBaseUrl);
    expect(findChannelValidationIssue(issues, { fields: ['models'] })?.code)
      .toBe(CHANNEL_VALIDATION_ISSUE_CODES.missingModels);
    expect(findChannelValidationIssue(issues, { fields: ['extra_headers'] })?.code)
      .toBe(CHANNEL_VALIDATION_ISSUE_CODES.missingExtraHeaders);
    expect(issues.every((issue) => /^[a-z0-9_]+$/.test(issue.code))).toBe(true);
  });

  it('keeps provider-specific empty-key and base-url rules on the legacy path', () => {
    expect(getChannelCompletenessIssues(
      channel({ providerId: 'ollama', protocol: 'ollama', apiKey: '', models: 'llama3' }),
      PROVIDERS,
      [],
    )).toEqual([]);
    expect(getChannelCompletenessIssues(
      channel({
        providerId: 'custom',
        protocol: 'openai',
        baseUrl: 'http://127.0.0.1:9000/v1',
        apiKey: '',
        models: 'local-model',
      }),
      PROVIDERS,
      ['127.0.0.1', 'localhost'],
    )).toEqual([]);
    expect(getChannelCompletenessIssues(
      channel({
        providerId: 'custom',
        protocol: 'openai',
        baseUrl: '',
        apiKey: '',
        models: '',
      }),
      PROVIDERS,
      [],
    )).toEqual([
      { code: CHANNEL_VALIDATION_ISSUE_CODES.missingApiKey, field: 'api_key' },
      { code: CHANNEL_VALIDATION_ISSUE_CODES.missingBaseUrl, field: 'base_url' },
      { code: CHANNEL_VALIDATION_ISSUE_CODES.missingModels, field: 'models' },
    ]);
  });

  it('keeps unknown schema conditions and unsupported fields visible as stable codes', () => {
    const unknownCondition = getChannelCompletenessIssues(
      channel(),
      PROVIDERS,
      [],
      withCoreFields([
        {
          key: 'models',
          dataType: 'array',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            enabledWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
          },
        },
      ]),
    );
    expect(unknownCondition).toEqual([
      { code: CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE },
    ]);

    const unsupportedField = getChannelCompletenessIssues(
      channel({ models: '' }),
      PROVIDERS,
      [],
      withCoreFields([
        { key: 'future_field', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
      ]),
    );
    expect(unsupportedField).toEqual([
      { code: CONNECTION_SCHEMA_UNAVAILABLE_ISSUE },
    ]);
  });

  it('blocks save on name issues before completeness, and on enabled completeness', () => {
    expect(getChannelSaveIssues(channel({ name: '' }), PROVIDERS, []).map((issue) => issue.code))
      .toEqual([CHANNEL_VALIDATION_ISSUE_CODES.nameRequired]);
    expect(getChannelDisplayNameIssues(channel({ displayName: '' }))).toEqual([
      { code: CHANNEL_VALIDATION_ISSUE_CODES.nameRequired, field: 'display_name' },
    ]);
    expect(getChannelSaveIssues(
      channel({ enabled: false, apiKey: '', models: '' }),
      PROVIDERS,
      [],
    )).toEqual([]);
    expect(getChannelSaveIssues(
      channel({ enabled: true, apiKey: '', models: '' }),
      PROVIDERS,
      [],
    ).map((issue) => issue.code)).toEqual([
      CHANNEL_VALIDATION_ISSUE_CODES.missingApiKey,
      CHANNEL_VALIDATION_ISSUE_CODES.missingModels,
    ]);
  });

  it('keeps every production renderer on structured codes plus localizeModelAccessIssue', () => {
    const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
    for (const relativePath of PRODUCTION_CALLERS) {
      const source = fs.readFileSync(path.join(webRoot, relativePath), 'utf8');
      expect(source, relativePath).toContain('localizeModelAccessIssue');
      expect(source, relativePath).not.toMatch(/连接名称必填|缺少 API 密钥|至少配置一个模型|连接 Schema/);
      expect(source, relativePath).not.toMatch(/codeByZh|localize by .*Chinese/i);
    }
    const modal = fs.readFileSync(
      path.join(webRoot, 'src/components/settings/LLMConnectionModal.tsx'),
      'utf8',
    );
    expect(modal).toContain('findChannelValidationIssue');
    expect(modal).toContain('error={nameError}');
    expect(modal).toContain('error={apiKeyError}');
    expect(modal).toContain('error={baseUrlError}');
    expect(modal).toContain('error={modelsError}');
    expect(modal).toContain('error={extraHeadersError}');
  });
});
