import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import type {
  AvailableModelEntry,
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
} from '../../types/systemConfig';
import { Button, CredentialInput, InlineAlert, Input, Modal, SearchableSelect, Select } from '../common';
import type { SearchableSelectOption } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { MODEL_ACCESS_TEXT, localizeModelAccessIssue } from '../../locales/settingsModelAccess';
import {
  type ConnectionCredentialField,
  evaluateConnectionSchemaAuthority,
  getProviderDisplayLabel,
  isConnectionModelDiscoveryEnabled,
  isConnectionSchemaFieldWritable,
  resolveConnectionRequirements,
  suggestConnectionName,
} from './llmConnectionContract';
import type { ChannelFieldSuffix } from '../../utils/modelAccessFieldKey';
import { isModelRef } from '../../utils/modelRef';
import { ProviderQuickLinks } from './ProviderQuickLinks';
import { getUiListSeparator } from '../../utils/uiLocale';
import { SETTINGS_CONTROL_WIDTH_CLASS } from './settingsControlLayout';
import { ModelMultiSelect } from './ModelMultiSelect';
import { SettingsSwitch } from './SettingsSwitch';
import {
  CONNECTION_FIELD_BY_DRAFT_KEY,
  CONNECTION_SCHEMA_UNAVAILABLE_ISSUE,
  CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE,
  areModelsEquivalent,
  buildChannelContractValues,
  buildProtocolOptions,
  canonicalizeHermesRouteModel,
  channelAllowsEmptyApiKey,
  channelIdentityCanWrite,
  collectChannelRouteSet,
  countChannelsForProvider,
  describeProviderOption,
  evaluateChannelSchemaAuthority,
  findCatalogProvider,
  formatProtocolLabel,
  getChannelCompletenessIssues,
  getChannelDisplayNameIssues,
  getChannelNameIssues,
  hasRuntimeOnlyMaskedHermesSecret,
  isHermesChannel,
  modelIdentityForConnection,
  normalizeModelForRuntime,
  normalizeProtocol,
  normalizeTaskReferenceRoute,
  preservesUnavailableProviderSnapshot,
  runChannelConnectionTest,
  runChannelModelDiscovery,
  shouldUseSavedHermesSecret,
  splitModels,
  toggleModelSelection,
  type ChannelConfig,
  type ChannelDiscoveryState,
  type ChannelTestState,
  type ModelReferenceReplacement,
  type TaskModelReference,
} from './llmChannelEditorModel';

interface ConnectionModalProps {
  mode: 'add' | 'edit';
  /** The channel being edited; null starts the add flow at the provider step. */
  initialChannel: ChannelConfig | null;
  focusModels?: boolean;
  focusField?: ChannelFieldSuffix;
  channels: ChannelConfig[];
  availableModelRoutes: string[];
  availableModels: AvailableModelEntry[];
  providers: LlmProviderCatalogEntry[];
  connectionFields?: LlmConnectionFieldSchema[];
  emptyApiKeyHosts: string[];
  maskToken: string;
  hermesSecretPersisted: boolean;
  catalogUnavailable: boolean;
  disabled: boolean;
  taskModelRefs: TaskModelReference[];
  onReloadCatalog?: () => void;
  onManageModels?: () => void;
  canReplaceModelReferences: boolean;
  onSubmit: (channel: ChannelConfig, replacements: ModelReferenceReplacement[]) => void;
  onClose: () => void;
}

// Two-step connection dialog: pick a provider from the catalog, then fill in
// only the fields that provider actually needs. Test / discovery failures stay
// inline — the dialog never closes on error.
const ConnectionModal: React.FC<ConnectionModalProps> = ({
  mode,
  initialChannel,
  focusModels = false,
  focusField,
  channels,
  availableModelRoutes,
  availableModels,
  providers,
  connectionFields,
  emptyApiKeyHosts,
  maskToken,
  hermesSecretPersisted,
  catalogUnavailable,
  disabled,
  taskModelRefs,
  onReloadCatalog,
  onManageModels,
  canReplaceModelReferences,
  onSubmit,
  onClose,
}) => {
  const { language } = useUiLanguage();
  const text = MODEL_ACCESS_TEXT[language];
  const hasConnectionSchema = connectionFields !== undefined;
  const connectionSchemaFields = connectionFields ?? [];
  const [draft, setDraft] = useState<ChannelConfig | null>(initialChannel);
  const [providerId, setProviderId] = useState<string | undefined>(() => (
    initialChannel?.providerId
  ));
  const provider = providerId ? findCatalogProvider(providers, providerId) : undefined;
  const preservesProviderSnapshot = Boolean(
    initialChannel
    && providerId
    && preservesUnavailableProviderSnapshot(providers, providerId, catalogUnavailable),
  );
  const isCustomService = provider ? provider.isCustom : !preservesProviderSnapshot;
  const [customBaseUrl, setCustomBaseUrl] = useState<boolean>(() => {
    if (!initialChannel) {
      return false;
    }
    const matchedProvider = findCatalogProvider(providers, initialChannel.providerId);
    if (!matchedProvider) {
      return preservesUnavailableProviderSnapshot(
        providers,
        initialChannel.providerId,
        catalogUnavailable,
      )
        ? initialChannel.baseUrl.trim() !== ''
        : true;
    }
    if (matchedProvider.isCustom) {
      return true;
    }
    if (matchedProvider.defaultBaseUrl) {
      return initialChannel.baseUrl.trim() !== '' && initialChannel.baseUrl !== matchedProvider.defaultBaseUrl;
    }
    return !hasConnectionSchema && matchedProvider.requiresBaseUrl
      ? true
      : initialChannel.baseUrl.trim() !== '';
  });
  const [showManualModelInput, setShowManualModelInput] = useState(false);
  const [modelDraft, setModelDraft] = useState('');
  const [keyVisible, setKeyVisible] = useState(false);
  const [test, setTest] = useState<ChannelTestState | null>(null);
  const [discovery, setDiscovery] = useState<ChannelDiscoveryState | null>(null);
  const [pendingModelRemoval, setPendingModelRemoval] = useState<null | {
    model: string;
    route: string;
    modelRef: string;
    references: TaskModelReference[];
  }>(null);
  const [replacementRoute, setReplacementRoute] = useState('');
  const [stagedReplacements, setStagedReplacements] = useState<ModelReferenceReplacement[]>([]);
  const testNonceRef = useRef(0);
  const discoveryNonceRef = useRef(0);

  const existingNames = useMemo(() => {
    const excluded = initialChannel?.name.trim().toLowerCase();
    return channels
      .map((channel) => channel.name.trim().toLowerCase())
      .filter((name) => name && name !== excluded);
  }, [channels, initialChannel]);

  const buildProviderDraft = (entry: LlmProviderCatalogEntry): ChannelConfig => {
    const candidate: ChannelConfig = {
      id: `modal:${entry.id}`,
      name: suggestConnectionName(existingNames, entry.id),
      displayName: getProviderDisplayLabel(entry, language),
      displayNameValuePresent: true,
      providerId: entry.id,
      providerIdExplicit: true,
      protocol: normalizeProtocol(entry.protocol),
      protocolValuePresent: true,
      baseUrl: entry.defaultBaseUrl ?? '',
      apiKey: '',
      credentialField: 'api_key',
      models: '',
      extraHeaders: '',
      enabled: true,
      enabledValuePresent: true,
    };
    if (hasConnectionSchema) {
      const authority = evaluateChannelSchemaAuthority(
        candidate,
        providers,
        emptyApiKeyHosts,
        connectionSchemaFields,
      );
      candidate.credentialField = (['api_key', 'api_keys'] as ConnectionCredentialField[])
        .find((key) => isConnectionSchemaFieldWritable(authority, key)) ?? 'api_key';
    }
    return candidate;
  };
  const providerCanBeSelected = (entry: LlmProviderCatalogEntry) => {
    if (disabled) {
      return false;
    }
    if (!hasConnectionSchema) {
      return true;
    }
    const candidate = buildProviderDraft(entry);
    if (mode === 'add') {
      return channelIdentityCanWrite(
        candidate,
        providers,
        emptyApiKeyHosts,
        connectionSchemaFields,
      );
    }
    const authority = evaluateChannelSchemaAuthority(
      candidate,
      providers,
      emptyApiKeyHosts,
      connectionSchemaFields,
    );
    return isConnectionSchemaFieldWritable(authority, 'provider_id');
  };
  const selectableProviders = providers.filter(providerCanBeSelected);
  const providerOptions: SearchableSelectOption[] = selectableProviders.map((entry) => {
      const count = countChannelsForProvider(channels, entry.id);
      return {
        value: entry.id,
        label: getProviderDisplayLabel(entry, language),
        sublabel: describeProviderOption(entry, count, language),
        keywords: [entry.protocol, ...entry.capabilities],
      };
    });
  const protocolOptions = useMemo(
    () => buildProtocolOptions(providers, draft?.protocol),
    [draft?.protocol, providers],
  );
  const officialProtocolOptions = buildProtocolOptions(
    provider ? [provider] : [],
    draft?.protocol,
  );

  const chooseProvider = (id: string) => {
    if (!id || !selectableProviders.some((entry) => entry.id === id)) {
      return;
    }
    setProviderId(id);
    testNonceRef.current += 1;
    discoveryNonceRef.current += 1;
    setTest(null);
    setDiscovery(null);
  };

  const changeDraftProvider = (id: string) => {
    if (
      disabled
      ||
      !draft
      || (
        hasConnectionSchema
        && !isConnectionSchemaFieldWritable(connectionAuthority, 'provider_id')
      )
    ) {
      return;
    }
    const chosen = findCatalogProvider(providers, id);
    if (!chosen) {
      return;
    }
    const previousProvider = findCatalogProvider(providers, draft.providerId);
    const shouldUseChosenDefault = !draft.baseUrl.trim()
      || Boolean(previousProvider?.defaultBaseUrl && draft.baseUrl === previousProvider.defaultBaseUrl);
    const nextBaseUrl = shouldUseChosenDefault ? (chosen.defaultBaseUrl ?? '') : draft.baseUrl;
    const proposedDraft: ChannelConfig = {
      ...draft,
      providerId: id,
      providerIdExplicit: true,
      protocol: normalizeProtocol(chosen.protocol),
      protocolValuePresent: true,
      baseUrl: nextBaseUrl,
    };
    const proposedAuthority = hasConnectionSchema
      ? evaluateChannelSchemaAuthority(
        proposedDraft,
        providers,
        emptyApiKeyHosts,
        connectionSchemaFields,
        {
          baseUrlVisible: Boolean(
            chosen.isCustom
            || (nextBaseUrl && (!chosen.defaultBaseUrl || nextBaseUrl !== chosen.defaultBaseUrl)),
          ),
        },
      )
      : evaluateConnectionSchemaAuthority({}, undefined);
    const proposedStates = proposedAuthority.states;
    if (
      hasConnectionSchema
      && !isConnectionSchemaFieldWritable(proposedAuthority, 'provider_id')
    ) {
      return;
    }
    const nextDraft: ChannelConfig = {
      ...draft,
      providerId: id,
      providerIdExplicit: true,
    };
    const canAdoptProviderDefault = (key: string) => !hasConnectionSchema
      || proposedStates[key] === undefined
      || proposedStates[key].visible === false
      || isConnectionSchemaFieldWritable(proposedAuthority, key);
    if (canAdoptProviderDefault('protocol')) {
      nextDraft.protocol = proposedDraft.protocol;
      nextDraft.protocolValuePresent = true;
    }
    if (canAdoptProviderDefault('base_url')) {
      nextDraft.baseUrl = proposedDraft.baseUrl;
    }
    setProviderId(id);
    setDraft(nextDraft);
    if (canAdoptProviderDefault('base_url')) {
      setCustomBaseUrl(Boolean(
        chosen.isCustom
        || (nextBaseUrl && (!chosen.defaultBaseUrl || nextBaseUrl !== chosen.defaultBaseUrl)),
      ));
    }
    testNonceRef.current += 1;
    discoveryNonceRef.current += 1;
    setTest(null);
    setDiscovery(null);
  };

  const advanceProvider = () => {
    if (disabled || !providerId) {
      return;
    }
    const chosen = findCatalogProvider(providers, providerId);
    if (!chosen || !providerCanBeSelected(chosen)) {
      return;
    }
    setDraft(buildProviderDraft(chosen));
    setCustomBaseUrl(chosen.isCustom === true);
    testNonceRef.current += 1;
    discoveryNonceRef.current += 1;
    setTest(null);
    setDiscovery(null);
  };

  const updateDraft = (field: keyof ChannelConfig, value: string | boolean) => {
    const schemaField = CONNECTION_FIELD_BY_DRAFT_KEY[field];
    if (schemaField && fieldIsReadOnly(schemaField)) {
      return;
    }
    setDraft((previous) => previous ? {
      ...previous,
      [field]: value,
      ...(field === 'displayName' ? { displayNameValuePresent: true } : {}),
      ...(field === 'protocol' ? { protocolValuePresent: true } : {}),
      ...(field === 'enabled' ? { enabledValuePresent: true } : {}),
    } : previous);
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
  const candidateChannels = useMemo(() => {
    if (!draft) {
      return channels;
    }
    return channels.some((channel) => channel.id === draft.id)
      ? channels.map((channel) => (channel.id === draft.id ? draft : channel))
      : [...channels, draft];
  }, [channels, draft]);
  const knownRouteSet = useMemo(() => new Set([
    ...availableModelRoutes,
    ...collectChannelRouteSet(candidateChannels, false),
  ]), [availableModelRoutes, candidateChannels]);
  const effectiveTaskModelRefs = useMemo(
    () => taskModelRefs.map((reference) => {
      let route = normalizeTaskReferenceRoute(reference, knownRouteSet);
      for (const replacement of stagedReplacements) {
        const replacementIncludesReference = replacement.references.some((candidate) => (
          candidate.key === reference.key
          && candidate.label === reference.label
          && normalizeTaskReferenceRoute(candidate, knownRouteSet) === replacement.fromRoute
        ));
        if (replacementIncludesReference && route === replacement.fromRoute) {
          route = replacement.toRoute;
        }
      }
      return { ...reference, route };
    }),
    [knownRouteSet, stagedReplacements, taskModelRefs],
  );
  const replacementOptions = useMemo<SearchableSelectOption[]>(() => {
    if (!draft || !pendingModelRemoval) {
      return [];
    }
    const seen = new Set<string>();
    const options: SearchableSelectOption[] = [];
    for (const channel of candidateChannels) {
      if (!channel.enabled) {
        continue;
      }
      for (const model of splitModels(channel.models)) {
        const route = isHermesChannel(channel)
          ? canonicalizeHermesRouteModel(model)
          : normalizeModelForRuntime(model, channel.protocol);
        const modelRef = modelIdentityForConnection(availableModels, channel.name, route);
        if (modelRef === pendingModelRemoval.modelRef || seen.has(modelRef)) {
          continue;
        }
        seen.add(modelRef);
        options.push({
          value: modelRef,
          label: model,
          sublabel: channel.displayName,
          keywords: [route, channel.name, channel.providerId],
        });
      }
    }
    return options;
  }, [availableModels, candidateChannels, draft, pendingModelRemoval]);
  const removeModel = (model: string) => {
    if (!draft || fieldIsReadOnly('models')) {
      return;
    }
    updateDraft('models', selectedModels.filter((existing) => existing !== model).join(','));
    setPendingModelRemoval(null);
    setReplacementRoute('');
  };
  const requestRemoveModel = (model: string) => {
    if (!draft || fieldIsReadOnly('models')) {
      return;
    }
    const route = isHermesChannel(draft)
      ? canonicalizeHermesRouteModel(model)
      : normalizeModelForRuntime(model, draft.protocol);
    const modelRef = modelIdentityForConnection(availableModels, draft.name, route);
    const references = effectiveTaskModelRefs.filter((reference) => (
      reference.route === modelRef
      || (!isModelRef(reference.route) && reference.route === route)
    ));
    if (references.length === 0) {
      removeModel(model);
      return;
    }
    setPendingModelRemoval({ model, route, modelRef, references });
    setReplacementRoute('');
  };
  const addModelToken = (raw: string) => {
    if (!draft || fieldIsReadOnly('models')) {
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
    if (!draft || disabled || !connectionContractKnown) {
      return;
    }
    if (hasRuntimeOnlyMaskedHermesSecret(draft, maskToken, hermesSecretPersisted)) {
      setTest({ status: 'error', text: text.runtimeSecret });
      return;
    }
    const nonce = testNonceRef.current + 1;
    testNonceRef.current = nonce;
    setTest({ status: 'loading', text: text.testing });
    const result = await runChannelConnectionTest(
      draft,
      shouldUseSavedHermesSecret(draft, maskToken, hermesSecretPersisted),
      language,
    );
    if (testNonceRef.current === nonce) {
      setTest(result);
    }
  };

  const handleDiscover = async () => {
    if (!draft || !discoveryEnabledByContract || modelsAreReadOnly) {
      return;
    }
    if (hasRuntimeOnlyMaskedHermesSecret(draft, maskToken, hermesSecretPersisted)) {
      setDiscovery({ status: 'error', text: text.runtimeSecret, models: discovery?.models || [] });
      return;
    }
    const nonce = discoveryNonceRef.current + 1;
    discoveryNonceRef.current = nonce;
    setDiscovery({ status: 'loading', text: text.loadingModels, models: discovery?.models || [] });
    const result = await runChannelModelDiscovery(
      draft,
      shouldUseSavedHermesSecret(draft, maskToken, hermesSecretPersisted),
      language,
    );
    if (discoveryNonceRef.current === nonce) {
      setDiscovery(result.status === 'error' && (discovery?.models.length || 0) > 0
        ? { ...result, models: discovery?.models || [] }
        : result);
    }
  };

  const nameIssues = draft ? getChannelNameIssues(draft) : [];
  const legacyDisplayNameIssues = draft
    ? getChannelDisplayNameIssues(draft, connectionFields)
    : [];
  const nameConflict = draft && existingNames.includes(draft.name.trim().toLowerCase())
    ? ['连接名称已存在，请更换']
    : [];
  const completenessIssues = draft
    ? getChannelCompletenessIssues(
      draft,
      providers,
      emptyApiKeyHosts,
      connectionFields,
      catalogUnavailable,
    )
    : [];
  const contractDiagnostics = completenessIssues.filter(
    (issue) => issue === CONNECTION_SCHEMA_UNAVAILABLE_ISSUE
      || issue === CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE,
  );
  const contractBlockingIssues = hasConnectionSchema
    ? completenessIssues
    : draft?.enabled
      ? completenessIssues
      : contractDiagnostics;
  const blockingIssues = [
    ...nameIssues,
    ...legacyDisplayNameIssues,
    ...nameConflict,
    ...contractBlockingIssues,
  ];
  const nameError = [
    ...legacyDisplayNameIssues,
    ...completenessIssues.filter((issue) => issue === '连接名称必填'),
    ...nameIssues,
    ...nameConflict,
  ][0];
  const apiKeyError = draft?.enabled ? completenessIssues.find((issue) => issue === '缺少 API 密钥') : undefined;
  const baseUrlError = draft?.enabled ? completenessIssues.find((issue) => issue === '缺少服务地址') : undefined;
  const modelsError = draft?.enabled ? completenessIssues.find((issue) => issue === '至少配置一个模型') : undefined;

  const providerRequirements = !hasConnectionSchema && draft && provider ? resolveConnectionRequirements({
    provider,
    protocol: draft.protocol,
    baseUrl: draft.baseUrl,
    emptyApiKeyHosts,
  }) : null;
  const connectionContractValues = draft ? buildChannelContractValues(
    draft,
    providers,
    emptyApiKeyHosts,
    {
      baseUrlVisible: isCustomService || customBaseUrl || focusField === 'BASE_URL',
      extraHeadersVisible: Boolean(draft.extraHeaders.trim() || focusField === 'EXTRA_HEADERS'),
    },
  ) : null;
  const connectionAuthority = evaluateConnectionSchemaAuthority(
    connectionContractValues ?? {},
    connectionFields,
  );
  const connectionFieldStates = connectionAuthority.states;
  const connectionContractKnown = connectionAuthority.usable;
  const fieldIsVisible = (key: string) => !hasConnectionSchema
    || connectionFieldStates[key]?.visible === true;
  const fieldIsReadOnly = (key: string) => disabled || !connectionAuthority.usable || (hasConnectionSchema
    && !isConnectionSchemaFieldWritable(connectionAuthority, key));
  const allowsEmptyKey = draft ? channelAllowsEmptyApiKey(draft, emptyApiKeyHosts) : false;
  const visibleApiKeyStates = hasConnectionSchema
    ? (['api_key', 'api_keys'] as ConnectionCredentialField[])
      .map((key) => ({ key, state: connectionFieldStates[key] }))
      .filter(({ state }) => state?.visible)
    : [];
  const writableCredentialFields = visibleApiKeyStates
    .filter(({ key }) => isConnectionSchemaFieldWritable(connectionAuthority, key))
    .map(({ key }) => key);
  const showApiKeyField = Boolean(draft) && (hasConnectionSchema
    ? visibleApiKeyStates.length > 0
    : providerRequirements?.showApiKey ?? true);
  const apiKeyRequired = hasConnectionSchema
    ? visibleApiKeyStates.some(({ state }) => state?.required)
    : !allowsEmptyKey;
  const apiKeyLabel = hasConnectionSchema && !apiKeyRequired
    ? text.apiKeyOptional
    : text.apiKey;
  const apiKeyIsReadOnly = hasConnectionSchema
    && (!connectionAuthority.usable || writableCredentialFields.length === 0);
  const showProtocolField = hasConnectionSchema
    ? connectionFieldStates.protocol?.visible === true
    : isCustomService || focusField === 'PROTOCOL';
  const showBaseUrlField = hasConnectionSchema
    ? connectionFieldStates.base_url?.visible === true
    : isCustomService || customBaseUrl || focusField === 'BASE_URL';
  const showExtraHeadersField = hasConnectionSchema
    ? fieldIsVisible('extra_headers')
    : focusField === 'EXTRA_HEADERS' || Boolean(draft?.extraHeaders.trim());
  const showModelsField = fieldIsVisible('models');
  const modelsAreReadOnly = fieldIsReadOnly('models');
  const baseUrlIsReadOnly = fieldIsReadOnly('base_url');
  const showEnabledField = fieldIsVisible('enabled');
  const supportsDiscovery = provider?.supportsDiscovery === true;
  const discoveryEnabledByContract = hasConnectionSchema
    ? Boolean(connectionContractValues && isConnectionModelDiscoveryEnabled(
      connectionContractValues,
      connectionSchemaFields,
    ))
    : true;
  const handleApiKeyChange = (nextValue: string) => {
    if (!draft) {
      return;
    }
    const preferred: ConnectionCredentialField = nextValue
      .split(',')
      .filter((segment) => segment.trim()).length > 1
      ? 'api_keys'
      : 'api_key';
    const nextCredentialField = hasConnectionSchema
      ? [preferred, draft.credentialField, ...writableCredentialFields]
        .find((key, index, candidates) => (
          candidates.indexOf(key) === index
          && writableCredentialFields.includes(key)
        ))
      : preferred;
    if (!nextCredentialField) {
      return;
    }
    setDraft({
      ...draft,
      apiKey: nextValue,
      credentialField: nextCredentialField,
    });
    testNonceRef.current += 1;
    discoveryNonceRef.current += 1;
    setTest(null);
    setDiscovery(null);
  };
  const revealedBaseUrlAuthority = draft && hasConnectionSchema
    ? evaluateChannelSchemaAuthority(
      draft,
      providers,
      emptyApiKeyHosts,
      connectionSchemaFields,
      {
        baseUrlVisible: true,
        extraHeadersVisible: Boolean(draft.extraHeaders.trim() || focusField === 'EXTRA_HEADERS'),
      },
    )
    : evaluateConnectionSchemaAuthority({}, connectionFields);
  const canRevealBaseUrl = !disabled && (!hasConnectionSchema
    || isConnectionSchemaFieldWritable(revealedBaseUrlAuthority, 'base_url'));
  const showBaseUrlSummary = !isCustomService
    && !customBaseUrl
    && !showBaseUrlField
    && canRevealBaseUrl;
  const discoveredModels = discovery?.models || [];
  const providerSelectId = 'connection-modal-provider';
  const nameInputId = 'connection-modal-name';
  const protocolInputId = 'connection-modal-protocol';
  const baseUrlInputId = 'connection-modal-base-url';
  const apiKeyInputId = 'connection-modal-api-key';
  const modelsInputId = 'connection-modal-models';
  const discoverButtonId = 'connection-modal-discover-models';
  const enabledSwitchId = 'connection-modal-enabled';
  const extraHeadersInputId = 'connection-modal-extra-headers';

  // A11y: focus the first form field (not the dialog close button) when the
  // dialog opens and when advancing from the provider step to the form step.
  // This child effect runs after the Modal's own focus move-in, so it wins.
  const focusStep = draft ? 'form' : 'provider';
  useEffect(() => {
    let targetId = providerSelectId;
    if (focusStep === 'form') {
      const requestedField = focusField ?? (focusModels ? 'MODELS' : undefined);
      if (requestedField === 'PROVIDER') {
        targetId = providerSelectId;
      } else if (requestedField === 'API_KEY' || requestedField === 'API_KEYS') {
        targetId = apiKeyInputId;
      } else if (requestedField === 'BASE_URL') {
        targetId = baseUrlInputId;
      } else if (requestedField === 'PROTOCOL') {
        targetId = protocolInputId;
      } else if (requestedField === 'MODELS') {
        targetId = !supportsDiscovery || showManualModelInput
          ? modelsInputId
          : discoverButtonId;
      } else if (requestedField === 'ENABLED') {
        targetId = enabledSwitchId;
      } else if (requestedField === 'EXTRA_HEADERS') {
        targetId = extraHeadersInputId;
      } else {
        targetId = nameInputId;
      }
    }
    document.getElementById(targetId)?.focus();
  }, [focusField, focusModels, focusStep, showManualModelInput, supportsDiscovery]);

  return (
    <Modal isOpen onClose={onClose} title={mode === 'edit' ? text.editService : text.addService} size="wide">
      {!draft ? (
        <div className="space-y-3">
          <p className="text-sm text-secondary-text">{text.chooseProviderDescription}</p>
          {catalogUnavailable || providers.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-danger">
              <span>{text.catalogFailed}</span>
              {onReloadCatalog ? (
                <button type="button" className="inline-flex min-h-11 min-w-11 items-center underline underline-offset-2" onClick={onReloadCatalog}>
                  {text.retry}
                </button>
              ) : null}
            </div>
          ) : providerOptions.length > 0 ? (
            <SearchableSelect
              id={providerSelectId}
              ariaLabel={text.chooseProvider}
              value={providerId ?? ''}
              onChange={chooseProvider}
              options={providerOptions}
              placeholder={text.providerPlaceholder}
              searchPlaceholder={text.providerSearch}
              disabled={disabled}
            />
          ) : null}
          <div className="flex items-center justify-end gap-2 pt-4">
            <Button type="button" variant="ghost" size="default" onClick={onClose}>{text.cancel}</Button>
            <Button
              type="button"
              variant="primary"
              size="default"
              disabled={
                !providerId
                || disabled
                || !selectableProviders.some((entry) => entry.id === providerId)
              }
              onClick={advanceProvider}
            >
              {text.next}
            </Button>
          </div>
        </div>
      ) : (
        // form wrapper (not div): password inputs outside a <form> trigger
        // browser DevTools warnings; all inner buttons are type="button".
        <form className="space-y-4" data-connection-id={draft.name} onSubmit={(event) => event.preventDefault()}>
          {mode === 'edit' && fieldIsVisible('provider_id') ? (
            <div>
              <label htmlFor={providerSelectId} className="mb-2 block text-sm font-medium text-foreground">
                {text.provider}
              </label>
              <SearchableSelect
                id={providerSelectId}
                ariaLabel={text.chooseProvider}
                value={providerId ?? ''}
                onChange={changeDraftProvider}
                options={providerOptions}
                placeholder={text.providerPlaceholder}
                searchPlaceholder={text.providerSearch}
                disabled={
                  catalogUnavailable
                  || providers.length === 0
                  || fieldIsReadOnly('provider_id')
                }
              />
              {catalogUnavailable ? <p className="mt-1 text-xs text-danger">{text.catalogFailed}</p> : null}
            </div>
          ) : null}
          {fieldIsVisible('display_name') ? (
            <div>
              <label htmlFor={nameInputId} className="mb-2 block text-sm font-medium text-foreground">
                {text.connectionName}
              </label>
              <Input
                id={nameInputId}
                value={draft.displayName}
                onChange={(e) => updateDraft('displayName', e.target.value)}
                placeholder={text.connectionName}
                error={nameError}
                disabled={fieldIsReadOnly('display_name')}
                fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
              />
            </div>
          ) : null}

          {showProtocolField ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor={protocolInputId} className="mb-2 block text-sm font-medium text-foreground">
                  {text.protocol}
                </label>
                <Select
                  id={protocolInputId}
                  value={draft.protocol}
                  onChange={(v) => updateDraft('protocol', normalizeProtocol(v))}
                  options={isCustomService ? protocolOptions : officialProtocolOptions}
                  placeholder={text.chooseProtocol}
                  disabled={fieldIsReadOnly('protocol')}
                  className={SETTINGS_CONTROL_WIDTH_CLASS}
                />
                {!isCustomService && provider ? (
                  <p className="mt-1 text-xs text-muted-text">
                    {formatUiText(text.providerProtocolRequired, { protocol: formatProtocolLabel(provider.protocol) })}
                  </p>
                ) : null}
              </div>
              {showBaseUrlField ? (
                <div>
                  <label htmlFor={baseUrlInputId} className="mb-2 block text-sm font-medium text-foreground">
                    {text.baseUrl}
                  </label>
                  <Input
                    id={baseUrlInputId}
                    value={draft.baseUrl}
                    onChange={(e) => updateDraft('baseUrl', e.target.value)}
                    placeholder="https://api.example.com/v1"
                    error={baseUrlError}
                    disabled={fieldIsReadOnly('base_url')}
                    fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
                  />
                </div>
              ) : null}
            </div>
          ) : showBaseUrlField ? (
            <div>
              <label htmlFor={baseUrlInputId} className="mb-2 block text-sm font-medium text-foreground">
                {text.baseUrl}
              </label>
              <Input
                id={baseUrlInputId}
                value={draft.baseUrl}
                onChange={(e) => updateDraft('baseUrl', e.target.value)}
                placeholder={provider?.defaultBaseUrl || 'https://api.example.com/v1'}
                error={baseUrlError}
                disabled={fieldIsReadOnly('base_url')}
                fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
              />
              {provider?.defaultBaseUrl ? (
                <button
                  type="button"
                  className="settings-accent-text mt-1 inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                  disabled={baseUrlIsReadOnly}
                  onClick={() => {
                    if (baseUrlIsReadOnly) {
                      return;
                    }
                    updateDraft('baseUrl', provider.defaultBaseUrl);
                    setCustomBaseUrl(false);
                  }}
                >
                  {text.restoreOfficialUrl}
                </button>
              ) : null}
            </div>
          ) : showBaseUrlSummary ? (
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-secondary-text">
              <span className="truncate">
                {provider?.defaultBaseUrl
                  ? text.officialUrl
                  : text.officialUrlHint}
              </span>
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center underline-offset-2 hover:underline"
                disabled={!canRevealBaseUrl}
                onClick={() => {
                  if (canRevealBaseUrl) {
                    setCustomBaseUrl(true);
                  }
                }}
              >
                {text.customUrl}
              </button>
            </div>
          ) : null}

          {showApiKeyField ? (
            <div>
              <label htmlFor={apiKeyInputId} className="mb-2 block text-sm font-medium text-foreground">
                {apiKeyLabel}
              </label>
              <CredentialInput
                id={apiKeyInputId}
                purpose="provider-secret"
                allowTogglePassword
                iconType="key"
                passwordVisible={keyVisible}
                onPasswordVisibleChange={setKeyVisible}
                value={draft.apiKey}
                onChange={(e) => handleApiKeyChange(e.target.value)}
                placeholder={apiKeyRequired ? text.multipleKeys : text.localKeyOptional}
                error={apiKeyError}
                disabled={apiKeyIsReadOnly}
              />
              <div className="mt-1">
                <ProviderQuickLinks
                  provider={provider}
                  context="credentials"
                  language={language}
                  primaryLabel={text.getKey.replace(/[:：]\s*$/, '')}
                  secondaryLabel={provider ? getProviderDisplayLabel(provider, language) : text.provider}
                />
              </div>
            </div>
          ) : null}

          {showExtraHeadersField ? (
            <div>
              <label htmlFor={extraHeadersInputId} className="mb-2 block text-sm font-medium text-foreground">
                {text.extraHeaders}
              </label>
              <Input
                id={extraHeadersInputId}
                value={draft.extraHeaders}
                onChange={(event) => updateDraft('extraHeaders', event.target.value)}
                placeholder={text.extraHeadersPlaceholder}
                disabled={fieldIsReadOnly('extra_headers')}
                fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
              />
            </div>
          ) : null}

          {showModelsField ? (
          <div className="space-y-2">
            <label htmlFor={modelsInputId} className="block text-sm font-medium text-foreground">
              {text.availableModels}
            </label>
            <ProviderQuickLinks
              provider={provider}
              context="models"
              language={language}
              primaryLabel={text.availableModels}
              secondaryLabel={provider ? getProviderDisplayLabel(provider, language) : text.viewDetails}
            />
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
                      aria-label={formatUiText(text.removeModel, { model })}
                      disabled={modelsAreReadOnly}
                      onClick={() => requestRemoveModel(model)}
                      className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted-text hover:text-danger"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
            {pendingModelRemoval ? (
              <InlineAlert
                variant="warning"
                size="compact"
                title={text.cannotDeleteModel}
                message={(
                  <div className="space-y-2">
                    <p>{text.modelReferenced}</p>
                    <ul className="ml-4 list-disc space-y-0.5">
                      {pendingModelRemoval.references.map((reference, index) => (
                        <li key={`${reference.key ?? reference.label}-${index}`}>{reference.label}</li>
                      ))}
                    </ul>
                    {canReplaceModelReferences && replacementOptions.length > 0 ? (
                      <div className="space-y-2">
                        <SearchableSelect
                          value={replacementRoute}
                          onChange={setReplacementRoute}
                          options={replacementOptions}
                          ariaLabel={text.replacementModel}
                          placeholder={text.chooseReplacement}
                          searchPlaceholder={text.searchReplacement}
                          disabled={modelsAreReadOnly}
                        />
                        <Button
                          type="button"
                          variant="primary"
                          size="default"
                          disabled={modelsAreReadOnly || !replacementRoute}
                          onClick={() => {
                            if (modelsAreReadOnly) {
                              return;
                            }
                            const replacements = Array.from(new Set(
                              pendingModelRemoval.references.map((reference) => reference.route),
                            )).map((fromRoute) => ({
                              fromRoute,
                              toRoute: replacementRoute,
                              references: pendingModelRemoval.references.filter((reference) => reference.route === fromRoute),
                            }));
                            setStagedReplacements((previous) => [
                              ...previous.filter((item) => !replacements.some((replacement) => replacement.fromRoute === item.fromRoute)),
                              ...replacements,
                            ]);
                            removeModel(pendingModelRemoval.model);
                          }}
                        >
                          {text.replaceAndDelete}
                        </Button>
                      </div>
                    ) : null}
                    {onManageModels ? (
                      <Button
                        type="button"
                        variant="secondary"
                        size="default"
                        onClick={onManageModels}
                      >
                        {text.goTaskRouting}
                      </Button>
                    ) : null}
                  </div>
                )}
              />
            ) : null}
            {supportsDiscovery ? (
              <>
                <div className="flex items-center gap-2">
                  <Button
                    id={discoverButtonId}
                    type="button"
                    variant="secondary"
                    size="default"
                    className="text-xs shadow-none"
                    disabled={
                      discovery?.status === 'loading'
                      || !discoveryEnabledByContract
                      || fieldIsReadOnly('models')
                    }
                    onClick={() => void handleDiscover()}
                  >
                    {discovery?.status === 'loading' ? text.gettingModels : text.getModels}
                  </Button>
                  <span className={`text-xs ${
                    discovery?.status === 'success'
                      ? 'text-success'
                      : discovery?.status === 'error'
                        ? 'text-danger'
                        : 'text-muted-text'
                  }`}
                  >
                    {discovery?.text || text.discoveryDescription}
                  </span>
                </div>
                {discovery?.hint ? <p className="text-xs text-secondary-text">{discovery.hint}</p> : null}
              </>
            ) : (
              <p className="text-xs text-muted-text">{text.noDiscovery}</p>
            )}
            {supportsDiscovery && discoveredModels.length > 0 ? (
              <ModelMultiSelect
                options={discoveredModels}
                isSelected={(model) => selectedModels.some((selectedModel) => (
                  areModelsEquivalent(selectedModel, model, draft.protocol)
                ))}
                onToggle={(model) => {
                  if (modelsAreReadOnly) {
                    return;
                  }
                  updateDraft('models', toggleModelSelection(draft.models, model, draft.protocol));
                }}
                disabled={modelsAreReadOnly}
              />
            ) : null}
            {showManualModelInput || !supportsDiscovery ? (
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
                  aria-label={text.addModelAria}
                  placeholder={text.addModelPlaceholder}
                  error={modelsError}
                  disabled={modelsAreReadOnly}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="default"
                  className="shrink-0 text-xs shadow-none"
                  disabled={!modelDraft.trim() || modelsAreReadOnly}
                  onClick={() => addModelToken(modelDraft)}
                >
                  {text.add}
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                disabled={modelsAreReadOnly}
                onClick={() => {
                  if (!modelsAreReadOnly) {
                    setShowManualModelInput(true);
                  }
                }}
              >
                {text.manualModel}
              </button>
            )}
          </div>
          ) : null}

          <div className="flex items-start gap-2">
            <Button
              type="button"
              variant="secondary"
              size="default"
              className="shrink-0 text-xs shadow-none"
                disabled={disabled || !connectionContractKnown || test?.status === 'loading'}
              onClick={() => void handleTest()}
            >
              {test?.status === 'loading' ? text.testing : text.testConnection}
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

          {showEnabledField ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-3 py-2.5">
            <div>
              <p className="text-sm text-foreground">{text.enableThis}</p>
              <p className="text-xs text-muted-text">{text.disabledDraftHint}</p>
            </div>
            <SettingsSwitch
              id={enabledSwitchId}
              checked={draft.enabled}
              disabled={fieldIsReadOnly('enabled')}
              onCheckedChange={(next) => updateDraft('enabled', next)}
              aria-label={text.enableAria}
              visualTestId="connection-enabled-switch-visual"
            />
          </div>
          ) : null}

          {blockingIssues.length > 0 ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={draft.enabled ? text.missingBeforeEnable : text.fixName}
              message={(
                <ul className="ml-4 list-disc space-y-0.5">
                  {blockingIssues.map((issue) => (
                    <li key={issue}>{localizeModelAccessIssue(issue, language)}</li>
                  ))}
                </ul>
              )}
            />
          ) : null}
          {!draft.enabled && completenessIssues.length > 0 ? (
            <p className="text-xs text-muted-text">{formatUiText(text.incompleteSavedDraft, { issues: completenessIssues.map((issue) => localizeModelAccessIssue(issue, language)).join(getUiListSeparator(language)) })}</p>
          ) : null}

          <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
            {mode === 'add' ? (
              <Button
                type="button"
                variant="ghost"
                size="default"
                onClick={() => {
                  setDraft(null);
                  setProviderId(undefined);
                  setTest(null);
                  setDiscovery(null);
                }}
              >
                {text.back}
              </Button>
            ) : null}
            <Button type="button" variant="ghost" size="default" onClick={onClose}>{text.cancel}</Button>
            <Button
              type="button"
              variant="primary"
              size="default"
              disabled={disabled || !connectionContractKnown || (
                mode === 'add'
                && !channelIdentityCanWrite(
                  draft,
                  providers,
                  emptyApiKeyHosts,
                  connectionFields,
                )
              ) || blockingIssues.length > 0}
              onClick={() => {
                if (
                  disabled
                  || !connectionContractKnown
                  || (
                    mode === 'add'
                    && !channelIdentityCanWrite(
                      draft,
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                    )
                  )
                ) {
                  return;
                }
                const finalChannels = candidateChannels.map((channel) => (
                  channel.id === draft.id ? draft : channel
                ));
                const finalRoutes = collectChannelRouteSet(finalChannels, true);
                onSubmit(
                  draft,
                  stagedReplacements.filter((replacement) => !finalRoutes.has(replacement.fromRoute)),
                );
              }}
            >
              {mode === 'edit' ? text.saveChanges : text.addToConfig}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};


export default ConnectionModal;
