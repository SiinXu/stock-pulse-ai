// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { LlmConnectionFieldSchema } from '../../types/systemConfig';
import {
  evaluateConnectionSchemaAuthority,
  inspectConnectionSchemaDefinition,
  isConnectionSchemaFieldWritable,
} from '../connectionSchemaAuthority';

const field = (
  key: string,
  contract: LlmConnectionFieldSchema['contract'] = { requirement: 'optional' },
): LlmConnectionFieldSchema => ({
  key,
  dataType: key === 'models' || key === 'api_keys'
    ? 'array'
    : key === 'enabled'
      ? 'boolean'
      : key === 'extra_headers'
        ? 'json'
        : 'string',
  isSensitive: false,
  isRequired: contract.requirement === 'required',
  contract,
});

const identityFields = [
  field('connection_name', { requirement: 'required' }),
  field('provider_id', { requirement: 'required' }),
];

const coreFields = [
  identityFields[0],
  field('display_name'),
  identityFields[1],
  field('protocol'),
  field('base_url'),
  field('api_key'),
  field('api_keys'),
  field('models'),
  field('extra_headers'),
  field('enabled', { requirement: 'required' }),
];

function withCoreFields(
  overrides: LlmConnectionFieldSchema[] = [],
): LlmConnectionFieldSchema[] {
  const byKey = new Map([...coreFields, ...overrides].map((entry) => [entry.key, entry]));
  return Array.from(byKey.values());
}

describe('Connection Schema authority', () => {
  it('reserves legacy compatibility for an omitted schema', () => {
    const definition = inspectConnectionSchemaDefinition(undefined);
    const authority = evaluateConnectionSchemaAuthority({}, undefined);

    expect(definition).toMatchObject({ mode: 'legacy', usable: true });
    expect(authority).toMatchObject({ mode: 'legacy', usable: true });
    expect(isConnectionSchemaFieldWritable(authority, 'models')).toBe(true);
  });

  it('fails closed for a present empty schema', () => {
    expect(inspectConnectionSchemaDefinition([])).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'empty',
    });
  });

  it('fails closed when either identity field is missing', () => {
    expect(inspectConnectionSchemaDefinition([field('models')])).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'missing_identity',
      missingIdentityFields: ['connection_name', 'provider_id'],
    });
    expect(inspectConnectionSchemaDefinition([field('connection_name'), field('models')]))
      .toMatchObject({
        mode: 'schema',
        usable: false,
        reason: 'missing_identity',
        missingIdentityFields: ['provider_id'],
      });
  });

  it('fails closed when a present schema contains identity fields but omits core fields', () => {
    expect(inspectConnectionSchemaDefinition(identityFields)).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'missing_core',
      missingCoreFields: [
        'display_name',
        'protocol',
        'base_url',
        'api_key',
        'api_keys',
        'models',
        'extra_headers',
        'enabled',
      ],
    });
  });

  it('fails closed without evaluating malformed runtime fields', () => {
    const malformedFields = [
      ...coreFields,
      null,
    ];

    expect(inspectConnectionSchemaDefinition(malformedFields)).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'malformed',
    });
    expect(evaluateConnectionSchemaAuthority({}, malformedFields)).toEqual({
      mode: 'schema',
      usable: false,
      reason: 'malformed',
      missingIdentityFields: [],
      states: {},
    });
  });

  it('accepts null optional members emitted by the Provider Catalog API', () => {
    const apiFields = withCoreFields([
      {
        key: 'connection_name',
        envSuffix: null,
        dataType: 'string',
        isSensitive: false,
        isRequired: true,
        contract: {
          requirement: 'required',
          requiredWhen: null,
          visibleWhen: null,
          enabledWhen: null,
          requiresConnectionTest: null,
        },
      },
      {
        key: 'provider_id',
        envSuffix: null,
        dataType: 'string',
        isSensitive: false,
        isRequired: true,
        contract: {
          requirement: 'required',
          requiredWhen: null,
          visibleWhen: null,
          enabledWhen: null,
          requiresConnectionTest: null,
        },
      },
      {
        key: 'models',
        envSuffix: 'MODELS',
        dataType: 'array',
        isSensitive: false,
        isRequired: false,
        contract: {
          requirement: 'optional',
          requiredWhen: [{ key: 'enabled', operator: 'notEmpty', value: null }],
          visibleWhen: null,
          enabledWhen: null,
          requiresConnectionTest: null,
        },
      },
    ]);

    expect(inspectConnectionSchemaDefinition(apiFields)).toMatchObject({
      mode: 'schema',
      usable: true,
    });
    expect(evaluateConnectionSchemaAuthority({}, apiFields)).toMatchObject({
      mode: 'schema',
      usable: true,
    });
  });

  it('rejects missing, empty, and non-object field contracts', () => {
    const baseField = {
      key: 'connection_name',
      dataType: 'string',
      isSensitive: false,
      isRequired: true,
    };
    const providerField = field('provider_id', { requirement: 'required' });

    expect(inspectConnectionSchemaDefinition([{ ...baseField }, providerField])).toMatchObject({
      usable: false,
      reason: 'malformed',
    });
    expect(inspectConnectionSchemaDefinition([
      { ...baseField, contract: {} },
      providerField,
    ])).toMatchObject({ usable: false, reason: 'malformed' });
    expect(inspectConnectionSchemaDefinition([
      { ...baseField, contract: [] },
      providerField,
    ])).toMatchObject({ usable: false, reason: 'malformed' });
  });

  it('rejects whitespace-padded field keys as malformed', () => {
    expect(inspectConnectionSchemaDefinition([
      { ...identityFields[0], key: ' connection_name' },
      identityFields[1],
    ])).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'malformed',
    });
    expect(inspectConnectionSchemaDefinition([
      ...identityFields,
      { ...field('models'), key: 'models ' },
    ])).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'malformed',
    });
  });

  it('rejects whitespace-padded condition keys as malformed', () => {
    expect(inspectConnectionSchemaDefinition([
      ...identityFields,
      field('models', {
        requirement: 'optional',
        enabledWhen: [{ key: ' provider_id ', operator: 'equals', value: 'openai' }],
      }),
    ])).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'malformed',
    });
  });

  it('fails closed when an identity field is inherited or conditionally writable', () => {
    const inherited = inspectConnectionSchemaDefinition(withCoreFields([
      field('provider_id', { requirement: 'inherited' }),
    ]));
    const conditional = inspectConnectionSchemaDefinition(withCoreFields([
      field('provider_id', {
        requirement: 'required',
        enabledWhen: [{ key: 'connection_name', operator: 'notEmpty' }],
      }),
    ]));

    expect(inherited).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'identity_read_only',
    });
    expect(conditional).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'identity_read_only',
    });
  });

  it('keeps a read-only non-identity field local to that field', () => {
    const authority = evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai', models: 'gpt-4o-mini' },
      withCoreFields([
        field('base_url', { requirement: 'inherited' }),
      ]),
    );

    expect(authority).toMatchObject({ mode: 'schema', usable: true });
    expect(isConnectionSchemaFieldWritable(authority, 'base_url')).toBe(false);
    expect(isConnectionSchemaFieldWritable(authority, 'models')).toBe(true);
  });

  it('fails closed when any field contains an unknown operator', () => {
    const authority = evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai', models: 'gpt-4o-mini' },
      withCoreFields([
        field('models', {
          requirement: 'optional',
          enabledWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
        }),
      ]),
    );

    expect(authority).toMatchObject({ mode: 'schema', usable: false, reason: 'unknown_condition' });
  });

  it('fails closed when an unknown schema field is visible and required', () => {
    const authority = evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai', future_token: '' },
      withCoreFields([
        field('future_token', { requirement: 'required' }),
      ]),
    );

    expect(authority).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'unsupported_required_field',
    });
  });

  it('fails closed when an unknown required field becomes conditionally visible', () => {
    const fields = withCoreFields([
      field('future_token', {
        requirement: 'required',
        visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'openai' }],
      }),
    ]);

    expect(inspectConnectionSchemaDefinition(fields)).toMatchObject({
      mode: 'schema',
      usable: true,
    });
    expect(evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai' },
      fields,
    )).toMatchObject({
      mode: 'schema',
      usable: false,
      reason: 'unsupported_required_field',
    });
  });

  it('accepts an unknown required field while it is conditionally hidden', () => {
    const fields = withCoreFields([
      field('future_token', {
        requirement: 'required',
        visibleWhen: [{ key: 'provider_id', operator: 'notEquals', value: 'openai' }],
      }),
    ]);

    expect(inspectConnectionSchemaDefinition(fields)).toMatchObject({
      mode: 'schema',
      usable: true,
    });
    expect(evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai' },
      fields,
    )).toMatchObject({ mode: 'schema', usable: true });
  });

  it('accepts a visible unknown field while it remains optional', () => {
    const fields = withCoreFields([
      field('future_hint', { requirement: 'optional' }),
    ]);

    expect(inspectConnectionSchemaDefinition(fields)).toMatchObject({
      mode: 'schema',
      usable: true,
    });
    expect(evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai' },
      fields,
    )).toMatchObject({ mode: 'schema', usable: true });
  });

  it('authorizes only schema-visible writable fields after identity authority is established', () => {
    const authority = evaluateConnectionSchemaAuthority(
      { connection_name: 'openai', provider_id: 'openai', models: 'gpt-4o-mini' },
      withCoreFields([
        field('base_url', {
          requirement: 'optional',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'other' }],
        }),
      ]),
    );

    expect(authority).toMatchObject({ mode: 'schema', usable: true });
    expect(isConnectionSchemaFieldWritable(authority, 'connection_name')).toBe(true);
    expect(isConnectionSchemaFieldWritable(authority, 'provider_id')).toBe(true);
    expect(isConnectionSchemaFieldWritable(authority, 'models')).toBe(true);
    expect(isConnectionSchemaFieldWritable(authority, 'base_url')).toBe(false);
  });
});
