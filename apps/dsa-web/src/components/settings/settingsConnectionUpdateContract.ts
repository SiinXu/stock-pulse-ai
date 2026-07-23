import type {
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
} from '../../types/systemConfig';
import {
  CONNECTION_SCHEMA_KEY_BY_SUFFIX,
  parseModelAccessFieldKey,
} from '../../utils/modelAccessFieldKey';
import {
  buildConnectionContractValues,
  evaluateConnectionSchemaAuthority,
  isConnectionSchemaFieldWritable,
  validateConnectionContractValues,
  type ConnectionCredentialField,
} from './llmConnectionContract';

export function connectionItemsRespectSchema(
  items: Array<{ key: string; value: string }>,
  currentValues: Record<string, string>,
  currentRawValueKeys: Set<string>,
  providers: LlmProviderCatalogEntry[],
  connectionFields: LlmConnectionFieldSchema[] | undefined,
  emptyApiKeyHosts: string[],
): boolean {
  if (connectionFields === undefined) {
    return true;
  }
  const parsedItems = items.flatMap((item) => {
    const parsed = parseModelAccessFieldKey(item.key);
    return parsed ? [{ item, parsed }] : [];
  });
  const channelsItem = items.find(
    (item) => item.key.trim().toUpperCase() === 'LLM_CHANNELS',
  );
  if (parsedItems.length === 0 && !channelsItem) {
    return true;
  }

  const valuesBefore = new Map(
    Object.entries(currentValues).map(([key, value]) => [key.toUpperCase(), value]),
  );
  const presentBefore = new Set(
    Array.from(currentRawValueKeys, (key) => key.toUpperCase()),
  );
  const valuesAfter = new Map(valuesBefore);
  const presentAfter = new Set(presentBefore);
  for (const item of items) {
    const key = item.key.toUpperCase();
    valuesAfter.set(key, item.value);
    presentAfter.add(key);
  }

  const connectionNames = (values: Map<string, string>) => (values.get('LLM_CHANNELS') ?? '')
    .split(',')
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
  const beforeNames = new Set(connectionNames(valuesBefore));
  const afterNames = new Set(connectionNames(valuesAfter));

  const buildAuthority = (
    connectionName: string,
    values: Map<string, string>,
    presentKeys: Set<string>,
    requireCatalogIdentity: boolean,
  ) => {
    const prefix = `LLM_${connectionName.toUpperCase()}_`;
    const value = (suffix: string) => {
      const key = `${prefix}${suffix}`;
      return presentKeys.has(key) ? (values.get(key) ?? '') : '';
    };
    const providerId = value('PROVIDER').trim();
    const provider = providers.find((candidate) => candidate.id === providerId);
    if (requireCatalogIdentity && !provider) {
      return null;
    }
    const apiKeys = value('API_KEYS');
    const credentialField: ConnectionCredentialField = apiKeys.trim()
      ? 'api_keys'
      : 'api_key';
    const rawEnabled = value('ENABLED').trim();
    const enabled = !['0', 'false', 'no', 'off'].includes(rawEnabled.toLowerCase());
    const authorityValues = buildConnectionContractValues({
      connectionName,
      displayName: value('DISPLAY_NAME'),
      providerId,
      provider,
      protocol: value('PROTOCOL'),
      baseUrl: value('BASE_URL'),
      apiKey: credentialField === 'api_keys' ? apiKeys : value('API_KEY'),
      credentialField,
      models: value('MODELS'),
      extraHeaders: value('EXTRA_HEADERS'),
      enabled,
      emptyApiKeyHosts,
    });
    // The shared builder accepts a boolean, so restore absence after building.
    authorityValues.enabled = rawEnabled ? authorityValues.enabled : '';
    return {
      authority: evaluateConnectionSchemaAuthority(authorityValues, connectionFields),
      values: authorityValues,
    };
  };

  const finalAuthorities = new Map<string, ReturnType<typeof buildAuthority>>();
  for (const connectionName of afterNames) {
    const result = buildAuthority(
      connectionName,
      valuesAfter,
      presentAfter,
      true,
    );
    if (
      !result
      || !result.authority.usable
      || validateConnectionContractValues(result.values, connectionFields).length > 0
    ) {
      return false;
    }
    finalAuthorities.set(connectionName, result);
  }

  for (const { parsed } of parsedItems) {
    const isActive = afterNames.has(parsed.connectionName);
    if (!isActive && !beforeNames.has(parsed.connectionName)) {
      return false;
    }
    const result = isActive
      ? finalAuthorities.get(parsed.connectionName)
      : buildAuthority(parsed.connectionName, valuesBefore, presentBefore, false);
    if (
      !result?.authority.usable
      || !isConnectionSchemaFieldWritable(
        result.authority,
        CONNECTION_SCHEMA_KEY_BY_SUFFIX[parsed.suffix],
      )
    ) {
      return false;
    }
  }

  if (channelsItem) {
    const affectedNames = new Set([...beforeNames, ...afterNames]);
    for (const connectionName of affectedNames) {
      const result = afterNames.has(connectionName)
        ? finalAuthorities.get(connectionName)
        : buildAuthority(connectionName, valuesBefore, presentBefore, false);
      if (
        !result?.authority.usable
        || !isConnectionSchemaFieldWritable(result.authority, 'connection_name')
      ) {
        return false;
      }
    }
  }

  return true;
}
