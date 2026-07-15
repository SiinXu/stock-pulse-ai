import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { getParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';
import { Badge, Button, ConfirmDialog, InlineAlert, Input, Modal, SearchableSelect, Select, StatusDot, Tooltip } from '../common';
import type { SearchableSelectOption } from '../common';
import type { ChannelProtocol } from './llmProviderTemplates';
import { getProviderPresentation } from './llmProviderTemplates';

// Provider *business* metadata comes from the backend catalog (passed as a
// prop). These helpers resolve an entry by channel/provider id; "known" excludes
// the generic custom provider (which ships no default endpoint/models).
function findCatalogProvider(
  providers: LlmProviderCatalogEntry[],
  id: string,
): LlmProviderCatalogEntry | undefined {
  return providers.find((provider) => provider.id === id);
}

function isKnownCatalogProvider(providers: LlmProviderCatalogEntry[], id: string): boolean {
  return id !== 'custom' && providers.some((provider) => provider.id === id);
}
import { ModelMultiSelect } from './ModelMultiSelect';

const PROTOCOL_OPTIONS: Array<{ value: ChannelProtocol; label: string }> = [
  { value: 'openai', label: 'OpenAI Compatible' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'vertex_ai', label: 'Vertex AI' },
  { value: 'ollama', label: 'Ollama' },
];

const KNOWN_MODEL_PREFIXES = new Set([
  'openai',
  'anthropic',
  'gemini',
  'vertex_ai',
  'deepseek',
  'minimax',
  'ollama',
  'cohere',
  'huggingface',
  'bedrock',
  'sagemaker',
  'azure',
  'replicate',
  'together_ai',
  'palm',
  'text-completion-openai',
  'command-r',
  'groq',
  'cerebras',
  'fireworks_ai',
  'friendliai',
]);

const CHANNEL_FIELD_SUFFIXES = ['PROTOCOL', 'BASE_URL', 'API_KEY', 'API_KEYS', 'MODELS', 'EXTRA_HEADERS', 'ENABLED'] as const;
const CHANNEL_FIELD_KEY_PATTERN = /^LLM_([A-Z0-9_]+)_(PROTOCOL|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$/;
const FALSEY_VALUES = new Set(['0', 'false', 'no', 'off']);
const HERMES_CHANNEL_NAME = 'hermes';
const HERMES_DEFAULT_MODEL = 'hermes-agent';

const isHermesChannel = (channel: Pick<ChannelConfig, 'name'>): boolean => (
  channel.name.trim().toLowerCase() === HERMES_CHANNEL_NAME
);

function canonicalizeHermesRouteModel(model: string): string {
  const trimmed = model.trim() || HERMES_DEFAULT_MODEL;
  return trimmed.startsWith('openai/') ? trimmed : `openai/${trimmed}`;
}

const shouldUseSavedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && hasPersistedSecret
);

const hasRuntimeOnlyMaskedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && !hasPersistedSecret
);

const RUNTIME_ONLY_HERMES_SECRET_MESSAGE = '运行时注入的密钥不会显示；如需在设置页测试，请重新输入 API 密钥。';

interface ChannelConfig {
  id: string;
  name: string;
  protocol: ChannelProtocol;
  baseUrl: string;
  apiKey: string;
  models: string;
  enabled: boolean;
}

interface ChannelTestState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
}

interface ChannelDiscoveryState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  models: string[];
}

interface RuntimeConfig {
  primaryModel: string;
  agentPrimaryModel: string;
  fallbackModels: string[];
  visionModel: string;
  temperature: string;
}

interface LLMChannelEditorProps {
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>;
  /** Authoritative provider catalog (business metadata) from the backend. */
  providers: LlmProviderCatalogEntry[];
  /** Hosts the backend exempts from API-key requirements (local endpoints). */
  emptyApiKeyHosts?: string[];
  maskToken: string;
  /** Parent-held channel draft, used to rehydrate after a tab-switch remount. */
  persistedDraftItems?: Array<{ key: string; value: string }>;
  onDraftItemsChange?: (items: Array<{ key: string; value: string }>) => void;
  /** Reports whether the current draft passes the structural completeness gate. */
  onValidityChange?: (valid: boolean) => void;
  /** Bumped by the parent to discard the local draft back to the saved snapshot. */
  resetSignal?: number;
  /** Bumped by the parent to open the "add connection" dialog. */
  addSignal?: number;
  disabled?: boolean;
  /**
   * The provider catalog failed to load. Existing connections stay editable/
   * read-only, but adding a NEW connection is blocked so we never create a
   * blank custom-like connection from a transient catalog outage.
   */
  catalogUnavailable?: boolean;
  /** Retry loading the provider catalog after a failure. */
  onReloadCatalog?: () => void;
  /** When a non-channels config source is effective, the editor is read-only. */
  overriddenByMode?: 'yaml' | 'legacy' | null;
  /** Jump to the developer diagnostics area for details on the config source. */
  onViewDiagnostics?: () => void;
  /** Task -> route references, to show which tasks use each connection. */
  taskModelRefs?: Array<{ label: string; route: string }>;
  /** Jump to the task-routing view to assign models to tasks. */
  onManageModels?: () => void;
}

function parseChannelFieldKeys(channel: ChannelConfig): string[] {
  const upperName = channel.name.trim().toUpperCase();
  return [
    `LLM_${upperName}_PROTOCOL`,
    `LLM_${upperName}_BASE_URL`,
    `LLM_${upperName}_ENABLED`,
    `LLM_${upperName}_API_KEY`,
    `LLM_${upperName}_API_KEYS`,
    `LLM_${upperName}_MODELS`,
    `LLM_${upperName}_EXTRA_HEADERS`,
  ];
}

function parseChannelFieldKeysFromName(name: string): string[] {
  const upperName = name.trim().toUpperCase();
  return CHANNEL_FIELD_SUFFIXES.map((suffix) => `LLM_${upperName}_${suffix}`);
}

function isChannelSecretFieldKey(key: string): boolean {
  const match = CHANNEL_FIELD_KEY_PATTERN.exec(key.toUpperCase());
  return match?.[2] === 'API_KEY' || match?.[2] === 'API_KEYS';
}

function resolveInitialChannelApiKeySource(
  channelName: string,
  initialItemValueByKey: Map<string, string>,
  initialItemSourceByKey: Map<string, boolean>,
): boolean | undefined {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (initialItemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (initialItemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue && initialItemSourceByKey.has(apiKeysKey)) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  if (apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }

  if (apiKeyValue) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  return initialItemSourceByKey.get(apiKeysKey) ?? initialItemSourceByKey.get(apiKeyKey);
}

function resolveInitialChannelApiKeyValue(
  channelName: string,
  itemValueByKey: Map<string, string>,
  itemSourceByKey: Map<string, boolean>,
): string {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (itemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (itemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue) {
    return apiKeyValue;
  }
  if (apiKeysValue && itemSourceByKey.has(apiKeysKey)) {
    return apiKeysValue;
  }
  if (apiKeyValue && itemSourceByKey.has(apiKeyKey)) {
    return apiKeyValue;
  }
  if (apiKeysValue) {
    return apiKeysValue;
  }
  if (apiKeyValue) {
    return apiKeyValue;
  }
  return itemValueByKey.get(apiKeysKey) || itemValueByKey.get(apiKeyKey) || '';
}

function buildChangedItemKeys(
  channels: ChannelConfig[],
  initialChannels: ChannelConfig[],
  initialItemSourceByKey: Map<string, boolean>,
  initialItemValueByKey: Map<string, string>,
): Set<string> {
  const changedKeys = new Set<string>();
  const nextChannelNames = channels.map((channel) => channel.name.trim().toLowerCase()).join(',');
  const previousChannelNames = initialChannels.map((channel) => channel.name.trim().toLowerCase()).join(',');

  if (nextChannelNames !== previousChannelNames) {
    changedKeys.add('LLM_CHANNELS');
  }

  const maxLength = Math.max(channels.length, initialChannels.length);
  for (let index = 0; index < maxLength; index += 1) {
    const current = channels[index];
    const previous = initialChannels[index];
    if (!current && !previous) {
      continue;
    }

    if (!current) {
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }
      continue;
    }

    if (!previous) {
      for (const key of parseChannelFieldKeys(current)) {
        changedKeys.add(key);
      }
      continue;
    }

    const currentName = current.name.trim().toUpperCase();
    const previousName = previous.name.trim().toUpperCase();
    if (currentName !== previousName) {
      const previousApiKeySource = resolveInitialChannelApiKeySource(
        previous.name,
        initialItemValueByKey,
        initialItemSourceByKey,
      );
      const preserveRuntimeOnlySecret = previousApiKeySource === false && current.apiKey === previous.apiKey;
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }

      for (const key of parseChannelFieldKeys(current)) {
        if (preserveRuntimeOnlySecret && isChannelSecretFieldKey(key)) {
          continue;
        }
        changedKeys.add(key);
      }
      continue;
    }

    const prefix = `LLM_${currentName}`;
    if (current.protocol !== previous.protocol) {
      changedKeys.add(`${prefix}_PROTOCOL`);
    }
    if (current.baseUrl !== previous.baseUrl) {
      changedKeys.add(`${prefix}_BASE_URL`);
    }
    if (current.enabled !== previous.enabled) {
      changedKeys.add(`${prefix}_ENABLED`);
    }
    if (current.apiKey !== previous.apiKey) {
      changedKeys.add(`${prefix}_API_KEY`);
      changedKeys.add(`${prefix}_API_KEYS`);
    }
    if (current.models !== previous.models) {
      changedKeys.add(`${prefix}_MODELS`);
    }
  }

  return changedKeys;
}

// A connection belongs to a catalog provider when its name is the provider id
// optionally followed by a numeric suffix (the auto-naming scheme used when
// adding a connection: "openai", "openai2", ...).
function matchProviderIdForChannelName(
  providers: LlmProviderCatalogEntry[],
  name: string,
): string | undefined {
  const lower = name.trim().toLowerCase();
  let best: string | undefined;
  for (const provider of providers) {
    if (provider.id === 'custom') {
      continue;
    }
    const id = provider.id.toLowerCase();
    const matches = lower === id || (lower.startsWith(id) && /^\d+$/.test(lower.slice(id.length)));
    if (matches && (!best || id.length > best.length)) {
      best = provider.id;
    }
  }
  return best;
}

function countChannelsForProvider(
  providers: LlmProviderCatalogEntry[],
  channels: ChannelConfig[],
  providerId: string,
): number {
  return channels.filter((channel) => {
    const matched = matchProviderIdForChannelName(providers, channel.name);
    if (providerId === 'custom') {
      return matched === undefined;
    }
    return matched === providerId;
  }).length;
}

// Suggest a unique connection name for a provider: the provider id itself,
// then a numeric suffix ("openai", "openai2", ...).
function suggestChannelName(existingNames: string[], providerId: string): string {
  const taken = new Set(existingNames.map((name) => name.trim().toLowerCase()));
  const base = providerId === 'custom' ? 'custom' : providerId.toLowerCase();
  if (!taken.has(base)) {
    return base;
  }
  let counter = 2;
  while (taken.has(`${base}${counter}`)) {
    counter += 1;
  }
  return `${base}${counter}`;
}

function describeProviderOption(entry: LlmProviderCatalogEntry, connectedCount: number): string {
  const protocol = normalizeProtocol(entry.protocol);
  const protocolLabel = PROTOCOL_OPTIONS.find((option) => option.value === protocol)?.label ?? entry.protocol;
  const purpose = entry.isLocal
    ? '连接本地模型服务'
    : entry.isCustom
      ? '接入兼容的自定义模型服务'
      : entry.capabilities.includes('aggregator')
        ? '接入聚合模型平台'
        : '接入云端模型服务';
  return `${protocolLabel} · ${purpose}${connectedCount > 0 ? ` · 已接入 ${connectedCount} 条` : ''}`;
}

// Shared connectivity-test runner used by the card quick action and the
// connection dialog (the dialog must keep failures inline without closing).
async function runChannelConnectionTest(
  channel: ChannelConfig,
  useSavedSecret: boolean,
): Promise<ChannelTestState> {
  try {
    const result = await systemConfigApi.testLLMChannel({
      name: channel.name,
      protocol: channel.protocol,
      baseUrl: channel.baseUrl,
      apiKey: channel.apiKey,
      models: splitModels(channel.models),
      enabled: channel.enabled,
      useSavedSecret,
    });
    if (result.success) {
      return {
        status: 'success',
        text: `连接成功${result.resolvedModel ? ` · ${result.resolvedModel}` : ''}${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`,
      };
    }
    return { status: 'error', text: buildLlmFailureText(result), hint: buildLlmTestHint(result) };
  } catch (error: unknown) {
    const parsed = getParsedApiError(error);
    return { status: 'error', text: parsed.message || '测试失败' };
  }
}

// Shared model-discovery runner. A successful call with an empty list is a
// distinct outcome (endpoint reachable but no model IDs) — not an error.
async function runChannelModelDiscovery(
  channel: ChannelConfig,
  useSavedSecret: boolean,
): Promise<ChannelDiscoveryState> {
  try {
    const result = await systemConfigApi.discoverLLMChannelModels({
      name: channel.name,
      protocol: channel.protocol,
      baseUrl: channel.baseUrl,
      apiKey: channel.apiKey,
      models: splitModels(channel.models),
      useSavedSecret,
    });
    if (result.success) {
      if (result.models.length === 0) {
        return {
          status: 'success',
          text: '服务已连通，但没有返回可用模型',
          hint: '请确认服务地址指向兼容的模型列表接口，或在下方手动添加模型。',
          models: [],
        };
      }
      return {
        status: 'success',
        text: `已获取 ${result.models.length} 个模型${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`,
        models: result.models,
      };
    }
    return {
      status: 'error',
      text: buildLlmFailureText(result),
      hint: getLlmTroubleshootingHint(result.errorCode, result.stage, 'discovery', result.details),
      models: [],
    };
  } catch (error: unknown) {
    const parsed = getParsedApiError(error);
    return { status: 'error', text: parsed.message || '获取模型失败', models: [] };
  }
}

interface ConnectionCardProps {
  channel: ChannelConfig;
  providers: LlmProviderCatalogEntry[];
  taskModelRefs: Array<{ label: string; route: string }>;
  unsaved: boolean;
  busy: boolean;
  testState?: ChannelTestState;
  issues: string[];
  onTest: () => void;
  onEdit: () => void;
  onManageModels: () => void;
  onToggleEnabled: () => void;
  onRemove: () => void;
}

// Compact connection card: provider, connection name, status, model chips and
// task usage plus quick actions. Credentials/endpoints/diagnostics live in the
// connection dialog, never on the card.
const ConnectionCard: React.FC<ConnectionCardProps> = ({
  channel,
  providers,
  taskModelRefs,
  unsaved,
  busy,
  testState,
  issues,
  onTest,
  onEdit,
  onManageModels,
  onToggleEnabled,
  onRemove,
}) => {
  const providerId = matchProviderIdForChannelName(providers, channel.name);
  const provider = providerId ? findCatalogProvider(providers, providerId) : undefined;
  const displayLabel = provider?.label ?? '自定义服务';
  const selectedModels = splitModels(channel.models);
  const channelRouteModels = resolveChannelRouteModels(channel);
  const usedByTasks = Array.from(
    new Set(
      taskModelRefs
        .filter((ref) => channelRouteModels.includes(ref.route))
        .map((ref) => ref.label),
    ),
  );
  const isComplete = issues.length === 0;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [menuOpen]);

  return (
    <div
      data-testid={`connection-card-${channel.name}`}
      className="rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-3 shadow-soft-card transition-[background-color,border-color] duration-200 hover:border-[var(--settings-border-strong)]"
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">{displayLabel}</span>
            <span className="truncate text-xs text-muted-text">{channel.name}</span>
            {unsaved ? <Badge variant="warning">未保存</Badge> : null}
            {!isComplete ? (
              <Tooltip content={issues.join('、')}>
                <span className="inline-flex">
                  <Badge variant="warning">草稿 · 未完成</Badge>
                </span>
              </Tooltip>
            ) : testState?.status === 'success' ? (
              <Badge variant="success">测试通过</Badge>
            ) : testState?.status === 'error' ? (
              <Badge variant="danger">测试失败</Badge>
            ) : testState?.status === 'loading' ? (
              <Badge variant="warning">测试中</Badge>
            ) : channel.enabled ? (
              <Badge variant="success">已启用</Badge>
            ) : (
              <Badge variant="default">已停用</Badge>
            )}
          </div>
          {selectedModels.length > 0 ? (
            <button
              type="button"
              aria-label={`管理模型 ${channel.name}`}
              onClick={onManageModels}
              disabled={busy}
              className="mt-1.5 flex max-w-full flex-wrap items-center gap-1 rounded-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed"
              data-testid={`connection-models-${channel.id}`}
            >
              {selectedModels.slice(0, 4).map((model) => (
                <span
                  key={model}
                  className="max-w-48 truncate rounded-full border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-1.5 py-0.5 text-xs text-secondary-text"
                >
                  {model}
                </span>
              ))}
              {selectedModels.length > 4 ? (
                <span className="text-xs text-muted-text">+{selectedModels.length - 4}</span>
              ) : null}
            </button>
          ) : (
            <button
              type="button"
              aria-label={`管理模型 ${channel.name}`}
              onClick={onManageModels}
              disabled={busy}
              className="mt-1.5 rounded-full text-left text-xs text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed"
            >
              尚未添加可用模型，点击此处获取或手动添加模型
            </button>
          )}
          {usedByTasks.length > 0 ? (
            <p className="mt-1 truncate text-xs text-muted-text">被以下任务使用：{usedByTasks.join('、')}</p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            type="button"
            variant="settings-secondary"
            size="sm"
            className="px-3 text-xs shadow-none"
            disabled={busy || testState?.status === 'loading'}
            onClick={onTest}
          >
            {testState?.status === 'loading' ? '测试中…' : '测试'}
          </Button>
          <Button
            type="button"
            variant="settings-secondary"
            size="sm"
            className="px-3 text-xs shadow-none"
            disabled={busy}
            onClick={onEdit}
          >
            编辑
          </Button>
          <div className="relative" ref={menuRef}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 px-2 text-xs text-muted-text"
              disabled={busy}
              aria-label={`更多操作 ${channel.name}`}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((previous) => !previous)}
            >
              ⋮
            </Button>
            {menuOpen ? (
              <div
                role="menu"
                className="absolute right-0 top-full z-20 mt-1 w-36 rounded-xl border border-border bg-elevated p-1 shadow-lg"
              >
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full rounded-full px-3 py-1.5 text-left text-xs text-foreground hover:bg-hover"
                  onClick={() => {
                    setMenuOpen(false);
                    onToggleEnabled();
                  }}
                >
                  {channel.enabled ? '停用连接' : '启用连接'}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full rounded-full px-3 py-1.5 text-left text-xs text-danger hover:bg-hover"
                  onClick={() => {
                    setMenuOpen(false);
                    onRemove();
                  }}
                >
                  删除连接
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {testState?.text ? (
        <div className="mt-2 flex items-start gap-1.5">
          <span className="mt-0.5 inline-flex">
            <StatusDot
              tone={testState.status === 'success' ? 'success' : testState.status === 'error' ? 'danger' : 'warning'}
              pulse={testState.status === 'loading'}
            />
          </span>
          <div className="min-w-0">
            <p className={`text-xs ${testState.status === 'success' ? 'text-success' : testState.status === 'error' ? 'text-danger' : 'text-muted-text'}`}>
              {testState.text}
            </p>
            {testState.hint ? <p className="text-xs text-secondary-text">{testState.hint}</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

interface ConnectionModalProps {
  mode: 'add' | 'edit';
  /** The channel being edited; null starts the add flow at the provider step. */
  initialChannel: ChannelConfig | null;
  focusModels?: boolean;
  channels: ChannelConfig[];
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
  maskToken: string;
  hermesSecretPersisted: boolean;
  catalogUnavailable: boolean;
  onReloadCatalog?: () => void;
  onSubmit: (channel: ChannelConfig) => void;
  onClose: () => void;
}

// Two-step connection dialog: pick a provider from the catalog, then fill in
// only the fields that provider actually needs. Test / discovery failures stay
// inline — the dialog never closes on error.
const ConnectionModal: React.FC<ConnectionModalProps> = ({
  mode,
  initialChannel,
  focusModels = false,
  channels,
  providers,
  emptyApiKeyHosts,
  maskToken,
  hermesSecretPersisted,
  catalogUnavailable,
  onReloadCatalog,
  onSubmit,
  onClose,
}) => {
  const [draft, setDraft] = useState<ChannelConfig | null>(initialChannel);
  const [providerId, setProviderId] = useState<string | undefined>(() => (
    initialChannel ? matchProviderIdForChannelName(providers, initialChannel.name) : undefined
  ));
  const provider = providerId ? findCatalogProvider(providers, providerId) : undefined;
  const isCustomService = !provider || provider.isCustom;
  const [customBaseUrl, setCustomBaseUrl] = useState<boolean>(() => {
    if (!initialChannel) {
      return false;
    }
    const matched = matchProviderIdForChannelName(providers, initialChannel.name);
    const matchedProvider = matched ? findCatalogProvider(providers, matched) : undefined;
    if (!matchedProvider || matchedProvider.isCustom) {
      return true;
    }
    if (matchedProvider.defaultBaseUrl) {
      return initialChannel.baseUrl.trim() !== '' && initialChannel.baseUrl !== matchedProvider.defaultBaseUrl;
    }
    return matchedProvider.requiresBaseUrl ? true : initialChannel.baseUrl.trim() !== '';
  });
  const [showManualModelInput, setShowManualModelInput] = useState(false);
  const [modelDraft, setModelDraft] = useState('');
  const [keyVisible, setKeyVisible] = useState(false);
  const [test, setTest] = useState<ChannelTestState | null>(null);
  const [discovery, setDiscovery] = useState<ChannelDiscoveryState | null>(null);
  const testNonceRef = useRef(0);
  const discoveryNonceRef = useRef(0);

  const existingNames = useMemo(() => {
    const excluded = initialChannel?.name.trim().toLowerCase();
    return channels
      .map((channel) => channel.name.trim().toLowerCase())
      .filter((name) => name && name !== excluded);
  }, [channels, initialChannel]);

  const providerOptions = useMemo<SearchableSelectOption[]>(() => {
    const options: SearchableSelectOption[] = [];
    for (const entry of providers) {
      if (entry.id === 'custom') {
        continue;
      }
      const count = countChannelsForProvider(providers, channels, entry.id);
      options.push({
        value: entry.id,
        label: entry.label,
        sublabel: describeProviderOption(entry, count),
        keywords: [entry.protocol, ...entry.capabilities],
      });
    }
    const customCount = countChannelsForProvider(providers, channels, 'custom');
    options.push({
      value: 'custom',
      label: '自定义服务',
      sublabel: `兼容服务 · 接入自定义模型服务${customCount > 0 ? ` · 已接入 ${customCount} 条` : ''}`,
    });
    return options;
  }, [providers, channels]);

  const chooseProvider = (id: string) => {
    if (!id) {
      return;
    }
    const chosen = findCatalogProvider(providers, id);
    setProviderId(id);
    setDraft({
      id: `modal:${id}`,
      name: suggestChannelName(existingNames, id),
      protocol: normalizeProtocol(chosen?.protocol ?? 'openai'),
      baseUrl: chosen?.defaultBaseUrl ?? '',
      apiKey: '',
      models: '',
      enabled: true,
    });
    setCustomBaseUrl(!chosen || chosen.isCustom === true);
    testNonceRef.current += 1;
    discoveryNonceRef.current += 1;
    setTest(null);
    setDiscovery(null);
  };

  const updateDraft = (field: keyof ChannelConfig, value: string | boolean) => {
    setDraft((previous) => (previous ? { ...previous, [field]: value } : previous));
    if (field === 'protocol' || field === 'baseUrl' || field === 'apiKey' || field === 'name') {
      // Bump nonces so in-flight test/discovery responses for the
      // previous connection parameters are discarded instead of re-filling state.
      testNonceRef.current += 1;
      discoveryNonceRef.current += 1;
      setTest(null);
      setDiscovery(null);
    }
  };

  const selectedModels = draft ? splitModels(draft.models) : [];
  const addModelToken = (raw: string) => {
    if (!draft) {
      return;
    }
    const tokens = raw.split(/[,\s]+/).map((token) => token.trim()).filter(Boolean);
    if (tokens.length === 0) {
      return;
    }
    let next = selectedModels;
    for (const token of tokens) {
      if (!next.some((existing) => areModelsEquivalent(existing, token, draft.protocol))) {
        next = [...next, token];
      }
    }
    if (next !== selectedModels) {
      updateDraft('models', next.join(','));
    }
    setModelDraft('');
  };

  const handleTest = async () => {
    if (!draft) {
      return;
    }
    if (hasRuntimeOnlyMaskedHermesSecret(draft, maskToken, hermesSecretPersisted)) {
      setTest({ status: 'error', text: RUNTIME_ONLY_HERMES_SECRET_MESSAGE });
      return;
    }
    const nonce = testNonceRef.current + 1;
    testNonceRef.current = nonce;
    setTest({ status: 'loading', text: '测试中…' });
    const result = await runChannelConnectionTest(
      draft,
      shouldUseSavedHermesSecret(draft, maskToken, hermesSecretPersisted),
    );
    if (testNonceRef.current === nonce) {
      setTest(result);
    }
  };

  const handleDiscover = async () => {
    if (!draft) {
      return;
    }
    if (hasRuntimeOnlyMaskedHermesSecret(draft, maskToken, hermesSecretPersisted)) {
      setDiscovery({ status: 'error', text: RUNTIME_ONLY_HERMES_SECRET_MESSAGE, models: discovery?.models || [] });
      return;
    }
    const nonce = discoveryNonceRef.current + 1;
    discoveryNonceRef.current = nonce;
    setDiscovery({ status: 'loading', text: '正在获取模型列表…', models: discovery?.models || [] });
    const result = await runChannelModelDiscovery(
      draft,
      shouldUseSavedHermesSecret(draft, maskToken, hermesSecretPersisted),
    );
    if (discoveryNonceRef.current === nonce) {
      setDiscovery(result.status === 'error' && (discovery?.models.length || 0) > 0
        ? { ...result, models: discovery?.models || [] }
        : result);
    }
  };

  const nameIssues = draft ? getChannelNameIssues(draft) : [];
  const nameConflict = draft && existingNames.includes(draft.name.trim().toLowerCase())
    ? ['连接名称已存在，请更换']
    : [];
  const completenessIssues = draft ? getChannelCompletenessIssues(draft, providers, emptyApiKeyHosts) : [];
  const blockingIssues = [...nameIssues, ...nameConflict, ...(draft?.enabled ? completenessIssues : [])];

  const allowsEmptyKey = draft ? channelAllowsEmptyApiKey(draft, emptyApiKeyHosts) : false;
  const showApiKeyField = Boolean(draft) && provider?.requiresApiKey !== false;
  const presentation = providerId ? getProviderPresentation(providerId) : undefined;
  const showBaseUrlSummary = !isCustomService && !customBaseUrl;
  const discoveredModels = discovery?.models || [];
  const providerSelectId = 'connection-modal-provider';
  const nameInputId = 'connection-modal-name';
  const protocolInputId = 'connection-modal-protocol';
  const baseUrlInputId = 'connection-modal-base-url';
  const apiKeyInputId = 'connection-modal-api-key';
  const modelsInputId = 'connection-modal-models';
  const discoverButtonId = 'connection-modal-discover-models';

  // A11y: focus the first form field (not the dialog close button) when the
  // dialog opens and when advancing from the provider step to the form step.
  // This child effect runs after the Modal's own focus move-in, so it wins.
  const focusStep = draft ? 'form' : 'provider';
  useEffect(() => {
    document.getElementById(
      focusStep === 'provider'
        ? providerSelectId
        : focusModels
          ? discoverButtonId
          : nameInputId,
    )?.focus();
  }, [focusStep, focusModels]);

  return (
    <Modal isOpen onClose={onClose} title={mode === 'edit' ? '编辑模型服务' : '添加模型服务'} className="max-w-xl">
      {!draft ? (
        <div className="space-y-3">
          <p className="text-sm text-secondary-text">选择要接入的模型服务商，下一步填写凭据并选择可用模型。</p>
          {catalogUnavailable || providers.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-danger">
              <span>模型服务列表加载失败</span>
              {onReloadCatalog ? (
                <button type="button" className="underline underline-offset-2" onClick={onReloadCatalog}>
                  重试
                </button>
              ) : null}
            </div>
          ) : (
            <SearchableSelect
              id={providerSelectId}
              ariaLabel="选择模型服务商"
              value=""
              onChange={chooseProvider}
              options={providerOptions}
              placeholder="搜索或选择服务商"
              searchPlaceholder="输入服务商名称搜索"
            />
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label htmlFor={nameInputId} className="mb-2 block text-sm font-medium text-foreground">
              连接名称
            </label>
            <Input
              id={nameInputId}
              value={draft.name}
              onChange={(e) => updateDraft('name', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
              placeholder="连接名称"
            />
          </div>

          {isCustomService ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor={protocolInputId} className="mb-2 block text-sm font-medium text-foreground">
                  协议
                </label>
                <Select
                  id={protocolInputId}
                  value={draft.protocol}
                  onChange={(v) => updateDraft('protocol', normalizeProtocol(v))}
                  options={PROTOCOL_OPTIONS}
                  placeholder="选择协议"
                />
              </div>
              <div>
                <label htmlFor={baseUrlInputId} className="mb-2 block text-sm font-medium text-foreground">
                  服务地址
                </label>
                <Input
                  id={baseUrlInputId}
                  value={draft.baseUrl}
                  onChange={(e) => updateDraft('baseUrl', e.target.value)}
                  placeholder="https://api.example.com/v1"
                />
              </div>
            </div>
          ) : showBaseUrlSummary ? (
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-secondary-text">
              <span className="truncate">
                {provider?.defaultBaseUrl
                  ? '使用服务商官方地址'
                  : '使用官方接口地址，无需填写。'}
              </span>
              <button
                type="button"
                className="settings-accent-text shrink-0 underline-offset-2 hover:underline"
                onClick={() => setCustomBaseUrl(true)}
              >
                使用自定义服务地址
              </button>
            </div>
          ) : (
            <div>
              <label htmlFor={baseUrlInputId} className="mb-2 block text-sm font-medium text-foreground">
                服务地址
              </label>
              <Input
                id={baseUrlInputId}
                value={draft.baseUrl}
                onChange={(e) => updateDraft('baseUrl', e.target.value)}
                placeholder={provider?.defaultBaseUrl || 'https://api.example.com/v1'}
              />
              {provider?.defaultBaseUrl ? (
                <button
                  type="button"
                  className="settings-accent-text mt-1 text-xs underline-offset-2 hover:underline"
                  onClick={() => {
                    updateDraft('baseUrl', provider.defaultBaseUrl);
                    setCustomBaseUrl(false);
                  }}
                >
                  恢复官方默认地址
                </button>
              ) : null}
            </div>
          )}

          {showApiKeyField ? (
            <div>
              <label htmlFor={apiKeyInputId} className="mb-2 block text-sm font-medium text-foreground">
                API 密钥
              </label>
              <Input
                id={apiKeyInputId}
                type="password"
                allowTogglePassword
                iconType="key"
                passwordVisible={keyVisible}
                onPasswordVisibleChange={setKeyVisible}
                value={draft.apiKey}
                onChange={(e) => updateDraft('apiKey', e.target.value)}
                placeholder={allowsEmptyKey ? '本地服务可留空' : '支持多个密钥，用逗号分隔'}
              />
              {presentation && presentation.officialSources.length > 0 ? (
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-text">
                  <span>获取密钥：</span>
                  {presentation.officialSources.map((source) => (
                    <a
                      key={source.url}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="settings-accent-text underline-offset-2 hover:underline"
                    >
                      {source.label}
                    </a>
                  ))}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            <label htmlFor={modelsInputId} className="block text-sm font-medium text-foreground">
              可用模型
            </label>
            {selectedModels.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {selectedModels.map((model) => (
                  <span
                    key={model}
                    className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-1.5 py-0.5 text-xs text-secondary-text"
                  >
                    <span className="truncate">{model}</span>
                    <button
                      type="button"
                      aria-label={`移除模型 ${model}`}
                      onClick={() => updateDraft('models', selectedModels.filter((existing) => existing !== model).join(','))}
                      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-muted-text hover:text-danger"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
            <div className="flex items-center gap-2">
              <Button
                id={discoverButtonId}
                type="button"
                variant="settings-secondary"
                size="sm"
                className="px-3 text-xs shadow-none"
                disabled={discovery?.status === 'loading'}
                onClick={() => void handleDiscover()}
              >
                {discovery?.status === 'loading' ? '获取中…' : '获取模型'}
              </Button>
              <span className={`text-xs ${
                discovery?.status === 'success'
                  ? 'text-success'
                  : discovery?.status === 'error'
                    ? 'text-danger'
                    : 'text-muted-text'
              }`}
              >
                {discovery?.text || '自动拉取该服务的可用模型，确认后再加入连接。'}
              </span>
            </div>
            {discovery?.hint ? <p className="text-xs text-secondary-text">{discovery.hint}</p> : null}
            {discoveredModels.length > 0 ? (
              <ModelMultiSelect
                options={discoveredModels}
                isSelected={(model) => selectedModels.some((selectedModel) => (
                  areModelsEquivalent(selectedModel, model, draft.protocol)
                ))}
                onToggle={(model) => updateDraft('models', toggleModelSelection(draft.models, model, draft.protocol))}
              />
            ) : null}
            {showManualModelInput ? (
              <div className="flex items-center gap-2">
                <Input
                  id={modelsInputId}
                  value={modelDraft}
                  onChange={(e) => setModelDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addModelToken(modelDraft);
                    }
                  }}
                  onPaste={(e) => {
                    const text = e.clipboardData.getData('text');
                    if (/[,\s]/.test(text.trim())) {
                      e.preventDefault();
                      addModelToken(`${modelDraft} ${text}`);
                    }
                  }}
                  aria-label="手动添加模型"
                  placeholder="输入模型 ID 后回车添加"
                />
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="sm"
                  className="shrink-0 px-3 text-xs shadow-none"
                  disabled={!modelDraft.trim()}
                  onClick={() => addModelToken(modelDraft)}
                >
                  添加
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="settings-accent-text text-xs underline-offset-2 hover:underline"
                onClick={() => setShowManualModelInput(true)}
              >
                没有找到需要的模型？手动添加模型
              </button>
            )}
          </div>

          <div className="flex items-start gap-2">
            <Button
              type="button"
              variant="settings-secondary"
              size="sm"
              className="shrink-0 px-3 text-xs shadow-none"
              disabled={test?.status === 'loading'}
              onClick={() => void handleTest()}
            >
              {test?.status === 'loading' ? '测试中…' : '测试连接'}
            </Button>
            {test?.text ? (
              <div className="min-w-0 space-y-0.5">
                <p className={`text-xs ${
                  test.status === 'success' ? 'text-success' : test.status === 'error' ? 'text-danger' : 'text-muted-text'
                }`}
                >
                  {test.text}
                </p>
                {test.hint ? <p className="text-xs text-secondary-text">{test.hint}</p> : null}
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-3 py-2.5">
            <div>
              <p className="text-sm text-foreground">启用此连接</p>
              <p className="text-xs text-muted-text">停用的连接会保留为草稿，不参与任务路由。</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={draft.enabled}
              aria-label="启用此连接"
              onClick={() => updateDraft('enabled', !draft.enabled)}
              className={`relative inline-flex h-5 w-8 shrink-0 items-center rounded-full transition-colors ${
                draft.enabled ? 'bg-foreground' : 'bg-border'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 rounded-full bg-background shadow-sm transition-transform ${
                  draft.enabled ? 'translate-x-3' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          {blockingIssues.length > 0 ? (
            <InlineAlert
              variant="warning"
              title={draft.enabled ? '启用前需补齐以下内容' : '连接名称需要修正'}
              message={(
                <ul className="ml-4 list-disc space-y-0.5">
                  {blockingIssues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
              className="rounded-lg px-3 py-2 text-xs shadow-none"
            />
          ) : null}
          {!draft.enabled && completenessIssues.length > 0 ? (
            <p className="text-xs text-muted-text">未补齐的内容会以草稿保存：{completenessIssues.join('、')}</p>
          ) : null}

          <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
            {mode === 'add' ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(null);
                  setProviderId(undefined);
                  setTest(null);
                  setDiscovery(null);
                }}
              >
                上一步
              </Button>
            ) : null}
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>取消</Button>
            <Button
              type="button"
              variant="settings-primary"
              size="sm"
              disabled={blockingIssues.length > 0}
              onClick={() => onSubmit(draft)}
            >
              {mode === 'edit' ? '保存修改' : '添加到配置'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
};

function normalizeProtocol(value: string): ChannelProtocol {
  const normalized = value.trim().toLowerCase().replace(/-/g, '_');
  if (normalized === 'vertex' || normalized === 'vertexai') {
    return 'vertex_ai';
  }
  if (normalized === 'claude') {
    return 'anthropic';
  }
  if (normalized === 'google') {
    return 'gemini';
  }
  if (normalized === 'deepseek') {
    return 'deepseek';
  }
  if (normalized === 'gemini') {
    return 'gemini';
  }
  if (normalized === 'anthropic') {
    return 'anthropic';
  }
  if (normalized === 'vertex_ai') {
    return 'vertex_ai';
  }
  if (normalized === 'ollama') {
    return 'ollama';
  }
  return 'openai';
}

function inferProtocol(protocol: string, baseUrl: string, models: string[]): ChannelProtocol {
  const explicit = normalizeProtocol(protocol);
  if (protocol.trim()) {
    return explicit;
  }

  const firstPrefixedModel = models.find((model) => model.includes('/'));
  if (firstPrefixedModel) {
    return normalizeProtocol(firstPrefixedModel.split('/', 1)[0]);
  }

  if (baseUrl.includes('127.0.0.1') || baseUrl.includes('localhost')) {
    return 'openai';
  }

  return 'openai';
}

function parseEnabled(value: string | undefined): boolean {
  if (!value) {
    return true;
  }
  return !FALSEY_VALUES.has(value.trim().toLowerCase());
}

function splitModels(models: string): string[] {
  return models
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

interface ParsedModelRef {
  name: string;
  provider: string;
  hasProvider: boolean;
}

function parseModelRef(model: string): ParsedModelRef {
  const trimmed = model.trim();
  if (!trimmed) {
    return { name: '', provider: '', hasProvider: false };
  }

  const delimiterIndex = trimmed.indexOf('/');
  if (delimiterIndex < 0) {
    return { name: trimmed.toLowerCase(), provider: '', hasProvider: false };
  }

  const rawProvider = trimmed.slice(0, delimiterIndex).trim();
  const name = trimmed.slice(delimiterIndex + 1).trim();
  if (!rawProvider || !name) {
    return { name: '', provider: '', hasProvider: false };
  }

  const lowerProvider = rawProvider.toLowerCase();
  return {
    name: name.toLowerCase(),
    provider: PROTOCOL_ALIASES[lowerProvider] || lowerProvider,
    hasProvider: true,
  };
}

function getModelComparisonKey(model: string, protocol: ChannelProtocol): string {
  const normalizedModel = normalizeModelForRuntime(model, protocol).trim();
  const parsed = parseModelRef(normalizedModel);
  if (!parsed.name) {
    return '';
  }
  return `${parsed.provider}/${parsed.name}`;
}

function areModelsEquivalent(a: string, b: string, protocol: ChannelProtocol): boolean {
  const left = getModelComparisonKey(a, protocol);
  const right = getModelComparisonKey(b, protocol);
  return left !== '' && left === right;
}

function toggleModelSelection(models: string, targetModel: string, protocol: ChannelProtocol): string {
  const selectedModels = splitModels(models);
  const index = selectedModels.findIndex((model) => areModelsEquivalent(model, targetModel, protocol));
  if (index >= 0) {
    return selectedModels.filter((_, itemIndex) => itemIndex !== index).join(',');
  }
  return [...selectedModels, targetModel].join(',');
}

const PROTOCOL_ALIASES: Record<string, string> = {
  vertexai: 'vertex_ai',
  vertex: 'vertex_ai',
  claude: 'anthropic',
  google: 'gemini',
  openai_compatible: 'openai',
  openai_compat: 'openai',
};

function normalizeModelForRuntime(model: string, protocol: ChannelProtocol): string {
  const trimmedModel = model.trim();
  if (!trimmedModel) {
    return trimmedModel;
  }

  if (trimmedModel.includes('/')) {
    const rawPrefix = trimmedModel.split('/', 1)[0].trim();
    const lowerPrefix = rawPrefix.toLowerCase();
    const canonicalPrefix = PROTOCOL_ALIASES[lowerPrefix] || lowerPrefix;
    if (KNOWN_MODEL_PREFIXES.has(lowerPrefix) || KNOWN_MODEL_PREFIXES.has(canonicalPrefix)) {
      if (canonicalPrefix !== lowerPrefix && KNOWN_MODEL_PREFIXES.has(canonicalPrefix)) {
        return `${canonicalPrefix}/${trimmedModel.split('/').slice(1).join('/')}`;
      }
      return trimmedModel;
    }
    return `${protocol}/${trimmedModel}`;
  }

  return `${protocol}/${trimmedModel}`;
}

function resolveModelPreview(models: string, protocol: ChannelProtocol): string[] {
  return splitModels(models).map((model) => normalizeModelForRuntime(model, protocol));
}

function resolveChannelRouteModels(channel: ChannelConfig): string[] {
  if (isHermesChannel(channel)) {
    const models = splitModels(channel.models);
    return (models.length > 0 ? models : [HERMES_DEFAULT_MODEL]).map(canonicalizeHermesRouteModel);
  }
  return resolveModelPreview(channel.models, channel.protocol);
}

const LLM_STAGE_LABELS: Record<string, string> = {
  model_discovery: '模型发现',
  chat_completion: '聊天调用',
  response_parse: '响应解析',
  capability_json: 'JSON 能力',
  capability_tools: 'Tools 能力',
  capability_stream: 'Stream 能力',
  capability_vision: 'Vision 能力',
};

const LLM_ERROR_LABELS: Record<string, string> = {
  auth: '鉴权失败',
  timeout: '请求超时',
  quota: '额度或限流',
  model_not_found: '模型不可用',
  request_blocked: '请求被拦截',
  empty_response: '空响应',
  format_error: '格式异常',
  network_error: '网络异常',
  invalid_config: '配置无效',
  unsupported_protocol: '协议暂不支持',
  capability_unsupported: '能力不支持',
  skipped: '已跳过',
};

const LLM_TROUBLESHOOTING_HINTS: Record<string, string> = {
  auth: '请检查 API 密钥是否正确、是否有多余空格，以及当前连接是否需要额外组织/项目权限。',
  timeout: '可重试；若持续超时，请检查服务地址、网络代理、服务商可用区或本地防火墙。',
  quota: '请检查余额、套餐额度、RPM/TPM 限流或并发设置，必要时稍后重试。',
  model_not_found: '请确认模型名与连接协议匹配，并先用“获取模型”核对该连接实际可用模型列表。',
  empty_response: '连接已连通但未返回正文；可尝试切换兼容模型、关闭额外响应模式后再测试。',
  network_error: '请检查服务地址、代理、TLS/证书、中转网关或本地网络策略，并可稍后重试。',
  invalid_config: '先补齐协议、服务地址、API 密钥和模型配置，再执行一键测试。',
  unsupported_protocol: '当前仅对 OpenAI Compatible / DeepSeek 连接提供自动模型发现，请改为手动维护模型列表。',
};

const LLM_REASON_HINTS: Record<string, string> = {
  missing_api_key: 'API 密钥为空，或逗号分隔后没有任何可用密钥；请填入至少一个有效密钥后再测试。',
  api_key_rejected: '服务商拒绝了当前 API 密钥；请检查密钥、组织/项目权限、区域和账号状态。',
  rate_limit: '服务商触发 RPM/TPM 或并发限流；请降低请求频率或稍后重试。',
  insufficient_balance: '服务商返回余额、账单或额度不足；请检查账户余额和套餐状态。',
  quota_exceeded: '服务商返回配额已耗尽；请确认账号套餐、余量和项目额度。',
  provider_blocked: '请求被服务商或中转网关拦截；请检查账号风控、地域限制、模型权限、代理商网关策略、内容安全策略或请求来源限制。',
  dns_error: '域名解析失败；请检查服务地址域名、网络代理和 DNS 配置。',
  tls_error: 'TLS/证书握手失败；请检查 HTTPS 证书、中转网关或公司代理策略。',
  connection_refused: '目标服务拒绝连接；请确认服务地址端口、服务进程和防火墙配置。',
  model_access_denied: '当前账号无法使用该模型；请确认模型是否已开通、账号是否可见，或模型是否已被禁用。',
  provider_prefix_mismatch: '模型 provider 前缀与当前连接不匹配；请确认模型名是否应使用该连接的 OpenAI-compatible 路由。',
  capability_unsupported: '当前模型或兼容层不支持该能力；这不影响基础文本连接，可换模型或关闭该能力依赖。',
};

function getLlmStageLabel(stage?: string | null): string {
  return LLM_STAGE_LABELS[stage || ''] || '连接测试';
}

function getLlmErrorCodeLabel(code?: string | null): string {
  return LLM_ERROR_LABELS[code || ''] || '测试失败';
}

function getLlmTroubleshootingHint(
  code?: string | null,
  stage?: string | null,
  context: 'test' | 'discovery' = 'test',
  details?: Record<string, unknown>,
): string | undefined {
  const reason = typeof details?.reason === 'string' ? details.reason : '';
  if (reason && LLM_REASON_HINTS[reason]) {
    return LLM_REASON_HINTS[reason];
  }
  if (code === 'format_error') {
    return context === 'discovery' || stage === 'model_discovery'
      ? '该连接返回的 /models 响应格式不兼容，请改为手动填写模型列表。'
      : '返回结构与预期不一致，请确认该连接兼容 Chat Completions 接口。';
  }
  if (code === 'empty_response' && (context === 'discovery' || stage === 'model_discovery')) {
    return '该连接的 /models 接口未返回可用模型 ID；请检查服务地址是否指向兼容的模型列表接口，或改为手动填写模型列表。';
  }
  return LLM_TROUBLESHOOTING_HINTS[code || ''];
}

function buildLlmTestHint(result: {
  errorCode?: string | null;
  stage?: string | null;
  details?: Record<string, unknown>;
  resolvedModel?: string | null;
}): string | undefined {
  const reason = typeof result.details?.reason === 'string' ? result.details.reason : '';
  const detailsModel = typeof result.details?.model === 'string' ? result.details.model : '';
  const testedModel = result.resolvedModel || detailsModel;
  const modelHint = testedModel ? `本次测试模型：${testedModel}。` : '';
  const scopeInfo = '基础连接测试默认只测试模型列表中的第一个模型。';
  const shouldSuggestModelListChange = reason === 'model_access_denied'
    || reason === 'model_not_found'
    || (result.errorCode === 'model_not_found' && !reason);
  const modelActionHint = shouldSuggestModelListChange
    ? '若该模型不可用，请调整模型顺序或移除不可用模型后重试。'
    : '';
  const troubleshootingHint = getLlmTroubleshootingHint(result.errorCode, result.stage, 'test', result.details);
  return [modelHint, scopeInfo, modelActionHint, troubleshootingHint].filter(Boolean).join(' ') || undefined;
}

function buildLlmFailureText(result: {
  message: string;
  error?: string | null;
  stage?: string | null;
  errorCode?: string | null;
}): string {
  const prefix = `${getLlmStageLabel(result.stage)} · ${getLlmErrorCodeLabel(result.errorCode)}`;
  const summary = result.message || '测试失败';
  if (result.error && result.error !== result.message) {
    return `${prefix}：${summary}（原始摘要：${result.error}）`;
  }
  return `${prefix}：${summary}`;
}

function runtimeConfigChangedKeys(left: RuntimeConfig, right: RuntimeConfig): Set<string> {
  const changed = new Set<string>();
  if (left.primaryModel !== right.primaryModel) {
    changed.add('LITELLM_MODEL');
  }
  if (left.agentPrimaryModel !== right.agentPrimaryModel) {
    changed.add('AGENT_LITELLM_MODEL');
  }
  if (left.fallbackModels.join(',') !== right.fallbackModels.join(',')) {
    changed.add('LITELLM_FALLBACK_MODELS');
  }
  if (left.temperature !== right.temperature) {
    changed.add('LLM_TEMPERATURE');
  }
  if (left.visionModel !== right.visionModel) {
    changed.add('VISION_MODEL');
  }
  return changed;
}

function resolveTemperatureFromItems(itemMap: Map<string, string>): string {
  const unified = itemMap.get('LLM_TEMPERATURE');
  if (unified) return unified;

  const primaryModel = itemMap.get('LITELLM_MODEL') || '';
  const provider = primaryModel.includes('/') ? primaryModel.split('/')[0] : (primaryModel ? 'openai' : '');
  const providerTemperatureEnv: Record<string, string> = {
    gemini: 'GEMINI_TEMPERATURE',
    vertex_ai: 'GEMINI_TEMPERATURE',
    anthropic: 'ANTHROPIC_TEMPERATURE',
    openai: 'OPENAI_TEMPERATURE',
    deepseek: 'OPENAI_TEMPERATURE',
  };
  const preferredEnv = providerTemperatureEnv[provider];
  if (preferredEnv) {
    const val = itemMap.get(preferredEnv);
    if (val) return val;
  }

  for (const envName of ['GEMINI_TEMPERATURE', 'ANTHROPIC_TEMPERATURE', 'OPENAI_TEMPERATURE']) {
    const val = itemMap.get(envName);
    if (val) return val;
  }

  return '0.7';
}

function normalizeAgentPrimaryModel(model: string): string {
  const trimmedModel = model.trim();
  if (!trimmedModel) {
    return '';
  }
  if (trimmedModel.includes('/')) {
    return trimmedModel;
  }
  return `openai/${trimmedModel}`;
}

function parseRuntimeConfigFromItems(items: Array<{ key: string; value: string }>): RuntimeConfig {
  const itemMap = new Map(items.map((item) => [item.key, item.value]));
  return {
    primaryModel: itemMap.get('LITELLM_MODEL') || '',
    agentPrimaryModel: normalizeAgentPrimaryModel(itemMap.get('AGENT_LITELLM_MODEL') || ''),
    fallbackModels: splitModels(itemMap.get('LITELLM_FALLBACK_MODELS') || ''),
    visionModel: itemMap.get('VISION_MODEL') || '',
    temperature: resolveTemperatureFromItems(itemMap),
  };
}

function parseChannelsFromItems(
  items: Array<{ key: string; value: string }>,
  itemSourceByKey: Map<string, boolean> = new Map(),
): ChannelConfig[] {
  const itemMap = new Map(items.map((item) => [item.key.toUpperCase(), item.value]));
  const channelNames = (itemMap.get('LLM_CHANNELS') || '')
    .split(',')
    .map((segment) => segment.trim())
    .filter(Boolean);

  return channelNames.map((name, index) => {
    const upperName = name.toUpperCase();
    const baseUrl = itemMap.get(`LLM_${upperName}_BASE_URL`) || '';
    const rawModels = itemMap.get(`LLM_${upperName}_MODELS`) || '';
    const models = splitModels(rawModels);

    return {
      id: `parsed:${index}:${upperName}`,
      name: name.toLowerCase(),
      protocol: inferProtocol(itemMap.get(`LLM_${upperName}_PROTOCOL`) || '', baseUrl, models),
      baseUrl,
      apiKey: resolveInitialChannelApiKeyValue(name, itemMap, itemSourceByKey),
      models: rawModels,
      enabled: parseEnabled(itemMap.get(`LLM_${upperName}_ENABLED`)),
    };
  });
}

function channelsToUpdateItems(
  channels: ChannelConfig[],
  previousChannelNames: string[],
  runtimeConfig: RuntimeConfig,
  includeRuntimeConfig: boolean,
): Array<{ key: string; value: string }> {
  const updates: Array<{ key: string; value: string }> = [];
  const activeNames = channels.map((channel) => channel.name.toUpperCase());

  updates.push({ key: 'LLM_CHANNELS', value: channels.map((channel) => channel.name).join(',') });
  if (includeRuntimeConfig) {
    updates.push({ key: 'LITELLM_MODEL', value: runtimeConfig.primaryModel });
    updates.push({ key: 'AGENT_LITELLM_MODEL', value: runtimeConfig.agentPrimaryModel });
    updates.push({ key: 'LITELLM_FALLBACK_MODELS', value: runtimeConfig.fallbackModels.join(',') });
    updates.push({ key: 'VISION_MODEL', value: runtimeConfig.visionModel });
    updates.push({ key: 'LLM_TEMPERATURE', value: runtimeConfig.temperature });
  }

  for (const channel of channels) {
    const prefix = `LLM_${channel.name.toUpperCase()}`;
    const isMultiKey = channel.apiKey.includes(',');
    updates.push({ key: `${prefix}_PROTOCOL`, value: channel.protocol });
    updates.push({ key: `${prefix}_BASE_URL`, value: channel.baseUrl });
    updates.push({ key: `${prefix}_ENABLED`, value: channel.enabled ? 'true' : 'false' });
    if (isHermesChannel(channel)) {
      updates.push({ key: `${prefix}_API_KEY`, value: channel.apiKey });
      updates.push({ key: `${prefix}_API_KEYS`, value: '' });
      updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: '' });
    } else {
      updates.push({ key: `${prefix}_API_KEY${isMultiKey ? 'S' : ''}`, value: channel.apiKey });
      updates.push({ key: `${prefix}_API_KEY${isMultiKey ? '' : 'S'}`, value: '' });
    }
    updates.push({ key: `${prefix}_MODELS`, value: channel.models });
  }

  for (const oldName of previousChannelNames) {
    const upperName = oldName.toUpperCase();
    if (activeNames.includes(upperName)) {
      continue;
    }

    const prefix = `LLM_${upperName}`;
    updates.push({ key: `${prefix}_PROTOCOL`, value: '' });
    updates.push({ key: `${prefix}_BASE_URL`, value: '' });
    updates.push({ key: `${prefix}_ENABLED`, value: '' });
    updates.push({ key: `${prefix}_API_KEY`, value: '' });
    updates.push({ key: `${prefix}_API_KEYS`, value: '' });
    updates.push({ key: `${prefix}_MODELS`, value: '' });
    updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: '' });
  }

  return updates;
}

function channelNamesAreSafe(channels: ChannelConfig[]): boolean {
  return channels.every((channel) => /^[a-z0-9_]+$/.test(channel.name.trim()));
}

// Structural completeness contract (Slice 1). Name/protocol must be valid for
// any channel; credential / base URL / models are required only when the
// channel is enabled. Connectivity testing is intentionally NOT a gate here.
function getChannelNameIssues(channel: ChannelConfig): string[] {
  const name = channel.name.trim();
  if (!name) {
    return ['连接名称必填'];
  }
  if (!/^[a-z0-9_]+$/.test(name)) {
    return ['连接名称仅限小写字母、数字或下划线'];
  }
  return [];
}

// Mirrors the backend `channel_allows_empty_api_key` contract: ollama never
// needs a key, and OpenAI-compatible endpoints on a backend-exempted local
// host (emptyApiKeyHosts) may leave it empty too.
function channelAllowsEmptyApiKey(
  channel: Pick<ChannelConfig, 'protocol' | 'baseUrl'>,
  emptyApiKeyHosts: string[],
): boolean {
  if (channel.protocol === 'ollama') {
    return true;
  }
  const baseUrl = channel.baseUrl.trim();
  if (!baseUrl) {
    return false;
  }
  try {
    return emptyApiKeyHosts.includes(new URL(baseUrl).hostname);
  } catch {
    return false;
  }
}

// Fields required to run the channel; surfaced as "未完成" while missing.
function getChannelCompletenessIssues(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
): string[] {
  const issues: string[] = [];
  if (!channelAllowsEmptyApiKey(channel, emptyApiKeyHosts) && !channel.apiKey.trim()) {
    issues.push('缺少 API 密钥');
  }
  // Known providers ship a default Base URL, and ollama/local endpoints have a
  // runtime default, so only custom remote endpoints must supply one. (The
  // backend completeness contract remains authoritative on save.)
  if (
    !isKnownCatalogProvider(providers, channel.name)
    && channel.protocol !== 'ollama'
    && !channel.baseUrl.trim()
  ) {
    issues.push('缺少服务地址');
  }
  if (splitModels(channel.models).length === 0) {
    issues.push('至少配置一个模型');
  }
  return issues;
}

// Issues that block saving: names must always be valid; enabled channels must
// additionally be complete. Disabled channels may be saved as drafts.
function getChannelSaveIssues(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
): string[] {
  const nameIssues = getChannelNameIssues(channel);
  if (nameIssues.length > 0) {
    return nameIssues;
  }
  return channel.enabled ? getChannelCompletenessIssues(channel, providers, emptyApiKeyHosts) : [];
}

function buildFilteredChannelUpdateItems({
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
}: {
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
}): Array<{ key: string; value: string }> {
  const changedKeys = new Set<string>([
    ...buildChangedItemKeys(channels, initialChannels, initialItemSourceByKey, savedItemMap),
    ...runtimeConfigChangedKeys(runtimeConfig, initialRuntimeConfig),
  ]);
  return channelsToUpdateItems(channels, initialNames, runtimeConfig, managesRuntimeConfig).filter((item) => {
    const itemKey = item.key.toUpperCase();
    const initialItemSource = initialItemSourceByKey.get(itemKey);
    if (initialItemSource === false) {
      return changedKeys.has(itemKey);
    }
    if (isChannelSecretFieldKey(itemKey) && initialItemSource === undefined) {
      return changedKeys.has(itemKey);
    }
    return true;
  });
}

function buildChannelDraftItems({
  hasChanges,
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
}: {
  hasChanges: boolean;
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
}): Array<{ key: string; value: string }> {
  if (!hasChanges || !channelNamesAreSafe(channels)) {
    return [];
  }
  return buildFilteredChannelUpdateItems({
    channels,
    initialChannels,
    initialNames,
    initialItemSourceByKey,
    savedItemMap,
    runtimeConfig,
    initialRuntimeConfig,
    managesRuntimeConfig,
  });
}

function channelsAreEqual(left: ChannelConfig, right: ChannelConfig): boolean {
  return (
    left.name === right.name
    && left.protocol === right.protocol
    && left.baseUrl === right.baseUrl
    && left.apiKey === right.apiKey
    && left.models === right.models
    && left.enabled === right.enabled
  );
}

function buildItemSourceByKey(
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>,
): Map<string, boolean> {
  const sourceByKey = new Map<string, boolean>();
  for (const item of items) {
    sourceByKey.set(item.key.toUpperCase(), item.rawValueExists !== false);
  }
  for (const [key, hasSource] of sourceByKey) {
    if (hasSource) {
      continue;
    }
    const match = CHANNEL_FIELD_KEY_PATTERN.exec(key);
    if (!match) {
      continue;
    }
    const channelName = match[1];
    for (const channelKey of parseChannelFieldKeysFromName(channelName)) {
      if (!sourceByKey.has(channelKey)) {
        sourceByKey.set(channelKey, false);
      }
    }
  }
  return sourceByKey;
}

// Layer the parent-held channel draft on top of the saved items so a remounted
// editor (after switching settings tabs) rehydrates the in-progress draft
// instead of dropping it. Draft entries win and are treated as user-provided.
function applyChannelDraftItems(
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>,
  draftItems: Array<{ key: string; value: string }> | undefined,
): Array<{ key: string; value: string; rawValueExists?: boolean }> {
  if (!draftItems || draftItems.length === 0) {
    return items;
  }
  const byKey = new Map<string, { key: string; value: string; rawValueExists?: boolean }>();
  for (const item of items) {
    byKey.set(item.key.toUpperCase(), { ...item });
  }
  for (const draftItem of draftItems) {
    const upperKey = draftItem.key.toUpperCase();
    const existing = byKey.get(upperKey);
    byKey.set(upperKey, {
      key: existing?.key ?? draftItem.key,
      value: draftItem.value,
      rawValueExists: true,
    });
  }
  return Array.from(byKey.values());
}

export const LLMChannelEditor: React.FC<LLMChannelEditorProps> = ({
  items,
  providers,
  emptyApiKeyHosts = [],
  maskToken,
  persistedDraftItems,
  onDraftItemsChange,
  onValidityChange,
  resetSignal = 0,
  addSignal = 0,
  disabled = false,
  catalogUnavailable = false,
  onReloadCatalog,
  overriddenByMode = null,
  onViewDiagnostics,
  taskModelRefs = [],
  onManageModels,
}) => {
  const initialItemSourceByKey = useMemo(() => buildItemSourceByKey(items), [items]);
  const initialChannels = useMemo(
    () => parseChannelsFromItems(items, initialItemSourceByKey),
    [items, initialItemSourceByKey],
  );
  const initialNames = useMemo(() => initialChannels.map((channel) => channel.name), [initialChannels]);
  const initialRuntimeConfig = useMemo(() => parseRuntimeConfigFromItems(items), [items]);
  const savedItemMap = useMemo(() => new Map(items.map((item) => [item.key.toUpperCase(), item.value])), [items]);
  const hermesSecretPersisted = initialItemSourceByKey.get('LLM_HERMES_API_KEY') === true;

  const channelsFingerprint = useMemo(() => JSON.stringify(initialChannels), [initialChannels]);
  const persistedDraftFingerprint = useMemo(
    () => JSON.stringify(persistedDraftItems ?? []),
    [persistedDraftItems],
  );

  const hydratedItems = useMemo(
    () => applyChannelDraftItems(items, persistedDraftItems),
    [items, persistedDraftItems],
  );
  const hydratedChannels = useMemo(
    () => parseChannelsFromItems(hydratedItems, buildItemSourceByKey(hydratedItems)),
    [hydratedItems],
  );

  const [channels, setChannels] = useState<ChannelConfig[]>(hydratedChannels);
  const [testStates, setTestStates] = useState<Record<string, ChannelTestState>>({});
  const [modal, setModal] = useState<null | { mode: 'add' } | { mode: 'edit'; index: number; focusModels?: boolean }>(null);
  const [pendingRemove, setPendingRemove] = useState<{ index: number; name: string; referencedBy: string[] } | null>(null);
  const addChannelIdRef = useRef(0);
  const testNonceRef = useRef<Record<string, number>>({});
  const testRequestIdRef = useRef(0);
  const lastDraftFingerprintRef = useRef<string | null>(null);
  const onValidityChangeRef = useRef(onValidityChange);

  const busy = disabled || Boolean(overriddenByMode);

  // Re-sync local state to the saved snapshot when it actually changes. Two
  // triggers: the saved config reloaded (typically after a successful Save &
  // Apply), the parent draft was committed/rehydrated (important when a saved
  // secret returns masked), or the parent bumped resetSignal on Discard. This
  // uses React's sanctioned "adjust state during render" reset-on-prop-change
  // pattern with prev-state, not an effect.
  const resetKey = `${channelsFingerprint}::${persistedDraftFingerprint}::${resetSignal}`;
  const [prevResetKey, setPrevResetKey] = useState(resetKey);
  if (prevResetKey !== resetKey) {
    setPrevResetKey(resetKey);
    setChannels(hydratedChannels);
    setTestStates({});
    setModal(null);
    setPendingRemove(null);
  }

  // The page-level "＋添加模型服务" button lives in the parent header; it bumps
  // addSignal to open the add dialog here (same adjust-during-render pattern).
  const [prevAddSignal, setPrevAddSignal] = useState(addSignal);
  if (prevAddSignal !== addSignal) {
    setPrevAddSignal(addSignal);
    if (!busy && !catalogUnavailable) {
      setModal({ mode: 'add' });
    }
  }

  const hasChanges = useMemo(() => {
    if (channels.length !== initialChannels.length) {
      return true;
    }
    return channels.some((channel, index) => !channelsAreEqual(channel, initialChannels[index]));
  }, [channels, initialChannels]);

  // Structural gate: names must be valid for every channel and every enabled
  // channel must be complete before the draft can be saved.
  const blockingChannels = useMemo(
    () => channels
      .map((channel, index) => ({ channel, index, issues: getChannelSaveIssues(channel, providers, emptyApiKeyHosts) }))
      .filter((entry) => entry.issues.length > 0),
    [channels, providers, emptyApiKeyHosts],
  );
  const draftValid = blockingChannels.length === 0;

  // Task Routing / Reliability own the runtime routing keys in this IA, so the
  // channel draft never emits them (managesRuntimeConfig: false).
  const draftItems = useMemo(() => buildChannelDraftItems({
    hasChanges,
    channels,
    initialChannels,
    initialNames,
    initialItemSourceByKey,
    savedItemMap,
    runtimeConfig: initialRuntimeConfig,
    initialRuntimeConfig,
    managesRuntimeConfig: false,
  }), [
    channels,
    hasChanges,
    initialChannels,
    initialItemSourceByKey,
    initialNames,
    initialRuntimeConfig,
    savedItemMap,
  ]);
  const draftFingerprint = useMemo(() => JSON.stringify(draftItems), [draftItems]);

  useEffect(() => {
    if (!onDraftItemsChange || lastDraftFingerprintRef.current === draftFingerprint) {
      return;
    }
    lastDraftFingerprintRef.current = draftFingerprint;
    onDraftItemsChange(draftItems);
  }, [draftFingerprint, draftItems, onDraftItemsChange]);

  // NOTE: the draft is intentionally NOT cleared on unmount. The parent owns the
  // unified draft and rehydrates it via persistedDraftItems when the editor
  // remounts (e.g. after a settings tab switch), so it must survive unmount.

  useEffect(() => {
    onValidityChangeRef.current = onValidityChange;
  }, [onValidityChange]);

  // Report the structural completeness gate up so the unified Save & Apply stays
  // blocked while an enabled channel is incomplete.
  useEffect(() => {
    onValidityChangeRef.current?.(draftValid);
  }, [draftValid]);

  // On unmount, clear any stale invalid state so a tab switch never leaves the
  // parent Save button blocked by an editor that is no longer mounted.
  useEffect(() => () => {
    onValidityChangeRef.current?.(true);
  }, []);

  const initialChannelsByName = useMemo(
    () => new Map(initialChannels.map((channel) => [channel.name, channel])),
    [initialChannels],
  );
  const isChannelUnsaved = (channel: ChannelConfig): boolean => {
    const saved = initialChannelsByName.get(channel.name);
    return !saved || !channelsAreEqual(channel, saved);
  };

  const handleTest = async (channel: ChannelConfig) => {
    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hermesSecretPersisted)) {
      setTestStates((previous) => ({
        ...previous,
        [channel.id]: { status: 'error', text: RUNTIME_ONLY_HERMES_SECRET_MESSAGE },
      }));
      return;
    }
    const requestId = testRequestIdRef.current + 1;
    testRequestIdRef.current = requestId;
    testNonceRef.current[channel.id] = requestId;
    setTestStates((previous) => ({
      ...previous,
      [channel.id]: { status: 'loading', text: '测试中…' },
    }));
    const result = await runChannelConnectionTest(
      channel,
      shouldUseSavedHermesSecret(channel, maskToken, hermesSecretPersisted),
    );
    if (testNonceRef.current[channel.id] !== requestId) {
      return;
    }
    setTestStates((previous) => ({ ...previous, [channel.id]: result }));
  };

  const clearTestState = (channelId: string) => {
    delete testNonceRef.current[channelId];
    setTestStates((previous) => {
      if (!(channelId in previous)) {
        return previous;
      }
      const next = { ...previous };
      delete next[channelId];
      return next;
    });
  };

  const removeChannel = (index: number) => {
    const removedChannelId = channels[index]?.id || '';
    setChannels((previous) => previous.filter((_, rowIndex) => rowIndex !== index));
    if (removedChannelId) {
      clearTestState(removedChannelId);
    }
  };

  // Deleting a channel drops its draft immediately, so confirm first. A
  // connection still backing a task-routing selection cannot be deleted here:
  // the confirm action becomes "go to Task Routing to replace" instead.
  const requestRemoveChannel = (index: number) => {
    const channel = channels[index];
    if (!channel) {
      return;
    }
    const routes = new Set(resolveChannelRouteModels(channel));
    const referencedBy = Array.from(new Set(
      taskModelRefs
        .filter((ref) => routes.has(ref.route))
        .map((ref) => ref.label),
    ));
    setPendingRemove({ index, name: channel.name.trim() || `#${index + 1}`, referencedBy });
  };

  // Enabling an incomplete connection opens the edit dialog instead of letting
  // an unusable connection go live.
  const toggleEnabled = (index: number) => {
    const channel = channels[index];
    if (!channel) {
      return;
    }
    if (!channel.enabled) {
      const issues = [
        ...getChannelNameIssues(channel),
        ...getChannelCompletenessIssues(channel, providers, emptyApiKeyHosts),
      ];
      if (issues.length > 0) {
        setModal({ mode: 'edit', index });
        return;
      }
    }
    setChannels((previous) => previous.map((item, rowIndex) => (
      rowIndex === index ? { ...item, enabled: !item.enabled } : item
    )));
  };

  const handleModalSubmit = (channel: ChannelConfig) => {
    if (!modal) {
      return;
    }
    if (modal.mode === 'add') {
      setChannels((previous) => [...previous, { ...channel, id: `added:${addChannelIdRef.current += 1}` }]);
    } else {
      const { index } = modal;
      const previousChannel = channels[index];
      if (previousChannel) {
        setChannels((previous) => previous.map((item, rowIndex) => (
          rowIndex === index ? { ...channel, id: item.id } : item
        )));
        const connectionChanged = previousChannel.name !== channel.name
          || previousChannel.protocol !== channel.protocol
          || previousChannel.baseUrl !== channel.baseUrl
          || previousChannel.apiKey !== channel.apiKey
          || previousChannel.models !== channel.models;
        if (connectionChanged) {
          clearTestState(previousChannel.id);
        }
      }
    }
    setModal(null);
  };

  return (
    <div className="space-y-4">
      {overriddenByMode ? (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-2.5 text-xs text-secondary-text">
          <span>当前模型配置由外部配置管理，网页暂时只读。</span>
          {onViewDiagnostics ? (
            <button
              type="button"
              className="settings-accent-text underline-offset-2 hover:underline"
              onClick={onViewDiagnostics}
            >
              查看详情
            </button>
          ) : null}
        </div>
      ) : null}

      {catalogUnavailable ? (
        <div className="flex items-center gap-2 px-1 text-xs text-danger">
          <span>模型服务列表加载失败</span>
          {onReloadCatalog ? (
            <button type="button" className="underline underline-offset-2" onClick={onReloadCatalog}>
              重试
            </button>
          ) : null}
        </div>
      ) : null}

      {channels.length === 0 ? (
        <div className="settings-surface-overlay-muted rounded-xl border border-dashed settings-border-strong px-4 py-10 text-center">
          <p className="text-sm font-medium text-secondary-text">还没有接入模型服务</p>
          <p className="mt-1 text-xs text-muted-text">接入后即可在任务路由中为报告、Agent 和视觉任务选择模型。</p>
          <Button
            type="button"
            variant="settings-primary"
            className="mt-4"
            disabled={busy || catalogUnavailable}
            onClick={() => setModal({ mode: 'add' })}
          >
            + 添加模型服务
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {channels.map((channel, index) => (
            <ConnectionCard
              key={channel.id}
              channel={channel}
              providers={providers}
              taskModelRefs={taskModelRefs}
              unsaved={isChannelUnsaved(channel)}
              busy={busy}
              testState={testStates[channel.id]}
              issues={[
                ...getChannelNameIssues(channel),
                ...getChannelCompletenessIssues(channel, providers, emptyApiKeyHosts),
              ]}
              onTest={() => void handleTest(channel)}
              onEdit={() => setModal({ mode: 'edit', index })}
              onManageModels={() => setModal({ mode: 'edit', index, focusModels: true })}
              onToggleEnabled={() => toggleEnabled(index)}
              onRemove={() => requestRemoveChannel(index)}
            />
          ))}
        </div>
      )}

      {!draftValid ? (
        <InlineAlert
          variant="warning"
          title="有模型服务未完成，无法保存"
          message={(
            <>
              <p className="mb-1">以下模型服务需补全后才能保存（点击顶部“保存并应用”统一提交）：</p>
              <ul className="ml-4 list-disc space-y-0.5">
                {blockingChannels.map(({ channel, index, issues }) => (
                  <li key={channel.id || index}>
                    {`${channel.name.trim() || `连接 #${index + 1}`}：${issues.join('、')}`}
                  </li>
                ))}
              </ul>
            </>
          )}
          className="rounded-lg px-3 py-2 text-xs shadow-none"
        />
      ) : null}

      {onManageModels && channels.some((channel) => channel.enabled) ? (
        <div className="flex items-center justify-end px-1">
          <button
            type="button"
            className="settings-accent-text text-xs underline-offset-2 hover:underline"
            onClick={onManageModels}
          >
            前往任务路由分配模型 →
          </button>
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={pendingRemove !== null}
        title={pendingRemove && pendingRemove.referencedBy.length > 0 ? '无法直接删除连接' : '删除连接？'}
        message={pendingRemove
          ? (pendingRemove.referencedBy.length > 0
            ? `模型服务「${pendingRemove.name}」正被以下任务引用：${pendingRemove.referencedBy.join('、')}。请先在任务路由为这些任务改选其它模型，再回来删除该连接（替换与删除会在同一次保存中一起提交）。`
            : `将从当前草稿中移除模型服务「${pendingRemove.name}」，保存后才生效。`)
          : ''}
        confirmText={pendingRemove && pendingRemove.referencedBy.length > 0 ? '前往任务路由替换' : '删除连接'}
        cancelText="取消"
        onConfirm={() => {
          if (pendingRemove) {
            if (pendingRemove.referencedBy.length > 0) {
              onManageModels?.();
            } else {
              removeChannel(pendingRemove.index);
            }
          }
          setPendingRemove(null);
        }}
        onCancel={() => setPendingRemove(null)}
      />

      {modal ? (
        <ConnectionModal
          mode={modal.mode}
          initialChannel={modal.mode === 'edit' ? channels[modal.index] ?? null : null}
          focusModels={modal.mode === 'edit' ? modal.focusModels : false}
          channels={channels}
          providers={providers}
          emptyApiKeyHosts={emptyApiKeyHosts}
          maskToken={maskToken}
          hermesSecretPersisted={hermesSecretPersisted}
          catalogUnavailable={catalogUnavailable}
          onReloadCatalog={onReloadCatalog}
          onSubmit={handleModalSubmit}
          onClose={() => setModal(null)}
        />
      ) : null}
    </div>
  );
};
