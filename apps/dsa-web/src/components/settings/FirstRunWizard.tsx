// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';
import {
  Button,
  CredentialInput,
  InlineAlert,
  Input,
  Modal,
  Select,
  type SearchableSelectOption,
} from '../common';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  LLMCapabilityCheck,
  LLMCapabilityCheckResult,
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
} from '../../types/systemConfig';
import { ModelMultiSelect } from './ModelMultiSelect';
import { ModelFallbackEditor } from './ModelFallbackEditor';
import {
  getLlmCapabilityLabel,
  type LlmConnectionCheckOutcome,
  runLlmConnectionCheck,
} from './llmChannelEditorModel';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import type { UiLang } from './settingsInformationArchitecture';
import {
  buildConnectionContractValues,
  canonicalModelRoute,
  type ConnectionCredentialField,
  evaluateConnectionSchemaAuthority,
  getProviderDisplayLabel,
  isConnectionModelDiscoveryEnabled,
  isConnectionSchemaFieldWritable,
  resolveConnectionRequirements,
  suggestConnectionName,
  validateConnectionContractValues,
} from './llmConnectionContract';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_WIZARD_TEXT } from '../../locales/settingsWizard';
import { decodeModelRef, encodeModelRef } from '../../utils/modelRef';
import { ProviderQuickLinks } from './ProviderQuickLinks';
import { SETTINGS_CONTROL_WIDTH_CLASS } from './settingsControlLayout';
import { LocalModelsPanel } from './LocalModelsPanel';

export interface WizardDraftItem {
  key: string;
  value: string;
}

export interface WizardCompleteResult {
  success: boolean;
  error?: string;
}

interface FirstRunWizardProps {
  /**
   * Commit the collected minimal config through the unified Save & Apply
   * transaction. Returns whether the backend accepted it so the wizard can keep
   * the modal open and show the error in place on failure.
   */
  onComplete: (items: WizardDraftItem[]) => Promise<WizardCompleteResult>;
  onClose: () => void;
  isSaving: boolean;
  language: UiLang;
  /**
   * Names already present in LLM_CHANNELS. A new Connection is merged into this
   * list instead of replacing it, so the wizard never clobbers existing setups.
   */
  existingChannelNames?: string[];
  /**
   * Authoritative provider catalog from the backend. The wizard reads provider
   * identity, labels, defaults, and capabilities from here. Field requirements
   * come from connectionFields when the backend supplies that schema.
   */
  providers: LlmProviderCatalogEntry[];
  connectionFields?: LlmConnectionFieldSchema[];
  emptyApiKeyHosts?: string[];
  /** Existing saved models that can be reused for fallback and vision routes. */
  routingOptions?: SearchableSelectOption[];
  initialFallbackModels?: string;
  initialVisionModel?: string;
  /** Opens the persistent Task Routing view after a successful save. */
  onViewRouting?: () => void;
  /** Refreshes Settings after the shared local-model panel persists configuration. */
  onLocalModelConfigurationChanged?: () => void | Promise<void>;
  /** Leaves setup for the canonical first-analysis workspace. */
  onStartFirstAnalysis?: () => void;
}

type WizardMode = 'cloud' | 'local_model' | 'cli';
type StepId = 'mode' | 'connection' | 'models' | 'model' | 'local_model' | 'review';

interface SavedWizardSummary {
  mode: WizardMode;
  execution: string;
  primaryModelRef: string;
  fallbackModels: string[];
  visionModel: string;
}

const CLI_BACKENDS: Array<{ value: string; label: string }> = [
  { value: 'claude_code_cli', label: 'Claude Code CLI' },
  { value: 'codex_cli', label: 'Codex CLI' },
  { value: 'opencode_cli', label: 'OpenCode CLI' },
];

const STEP_ORDER: Record<WizardMode, StepId[]> = {
  cloud: ['mode', 'connection', 'models', 'model', 'review'],
  local_model: ['mode', 'local_model', 'review'],
  cli: ['mode', 'connection', 'review'],
};

// Capabilities validated during the optional connection test: JSON structured
// output (reports/decision signals) and Vision (screenshot/image analysis).
// The backend reports these without changing the base connectivity verdict.
const WIZARD_CAPABILITY_CHECKS: LLMCapabilityCheck[] = ['json', 'vision'];

function parseModels(models: string): string[] {
  return models
    .split(',')
    .map((model) => model.trim())
    .filter((model) => model.length > 0);
}

/**
 * Minimal first-run configuration wizard. It only collects the smallest set of
 * fields needed for a runnable config (one enabled channel + models, or a local
 * CLI backend) and commits them to the unified draft via onComplete, then the
 * page runs the normal Save & Apply. Advanced fields never appear here.
 */
export const FirstRunWizard: React.FC<FirstRunWizardProps> = ({
  onComplete,
  onClose,
  isSaving,
  language,
  existingChannelNames = [],
  providers,
  connectionFields,
  emptyApiKeyHosts = [],
  routingOptions: existingRoutingOptions = [],
  initialFallbackModels = '',
  initialVisionModel = '',
  onViewRouting,
  onLocalModelConfigurationChanged,
  onStartFirstAnalysis,
}) => {
  const text = SETTINGS_WIZARD_TEXT[language];
  const [step, setStep] = useState<StepId>('mode');
  const [mode, setMode] = useState<WizardMode | null>(null);
  const [providerId, setProviderId] = useState<string>(providers[0]?.id ?? '');
  const [protocol, setProtocol] = useState(providers[0]?.protocol ?? 'openai');
  const [apiKey, setApiKey] = useState('');
  const [credentialField, setCredentialField] = useState<ConnectionCredentialField>('api_key');
  const [baseUrl, setBaseUrl] = useState('');
  const [models, setModels] = useState('');
  const [modelDraft, setModelDraft] = useState('');
  const [reportModel, setReportModel] = useState('');
  const [fallbackModels, setFallbackModels] = useState(initialFallbackModels);
  const [visionModel, setVisionModel] = useState(initialVisionModel);
  const [cliBackend, setCliBackend] = useState('');
  const [localModelReady, setLocalModelReady] = useState('');
  // Discovery results are candidates only: the user confirms which ones to
  // enable via the multi-select — never auto-selected wholesale.
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoverNote, setDiscoverNote] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmConnectionCheckOutcome | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedSummary, setSavedSummary] = useState<SavedWizardSummary | null>(null);
  const connectionTestVersionRef = useRef(0);
  const discoveryVersionRef = useRef(0);

  // Resolve the selected provider against the backend catalog. If the stored id
  // is stale (catalog re-loaded), fall back to the first available provider.
  const provider = useMemo(
    () => providers.find((entry) => entry.id === providerId) ?? providers[0],
    [providers, providerId],
  );
  const modelOptions = useMemo(() => parseModels(models), [models]);
  const suggestedConnectionName = useMemo(
    () => provider ? suggestConnectionName(existingChannelNames, provider.id) : '',
    [existingChannelNames, provider],
  );
  const modelRefFor = useCallback((model: string): string => {
    const route = canonicalModelRoute(protocol, model);
    return route ? encodeModelRef(suggestedConnectionName, route) : '';
  }, [protocol, suggestedConnectionName]);
  const effectivePrimaryModel = reportModel || modelOptions[0] || '';
  const effectivePrimaryModelRef = modelRefFor(effectivePrimaryModel);
  const draftRoutingOptions = useMemo<SearchableSelectOption[]>(() => modelOptions.map((model) => ({
    value: modelRefFor(model),
    label: model,
    sublabel: [
      provider ? getProviderDisplayLabel(provider, language) : '',
      suggestedConnectionName,
    ].filter(Boolean).join(' · ') || undefined,
    group: suggestedConnectionName || undefined,
    keywords: [model, protocol, suggestedConnectionName].filter(Boolean),
  })).filter((option) => Boolean(option.value)), [
    language,
    modelRefFor,
    modelOptions,
    protocol,
    provider,
    suggestedConnectionName,
  ]);
  const routingOptions = useMemo<SearchableSelectOption[]>(() => {
    const byValue = new Map<string, SearchableSelectOption>();
    for (const option of [...existingRoutingOptions, ...draftRoutingOptions]) {
      byValue.set(option.value, option);
    }
    for (const value of [...parseModels(initialFallbackModels), initialVisionModel].filter(Boolean)) {
      if (!byValue.has(value)) {
        const decoded = decodeModelRef(value);
        byValue.set(value, {
          value,
          label: decoded?.runtimeRoute ?? value,
          sublabel: decoded?.connectionId,
        });
      }
    }
    return Array.from(byValue.values());
  }, [draftRoutingOptions, existingRoutingOptions, initialFallbackModels, initialVisionModel]);
  const hasConnectionSchema = connectionFields !== undefined;
  const connectionSchemaFields = connectionFields ?? [];
  const requirements = useMemo(() => !hasConnectionSchema && provider ? resolveConnectionRequirements({
    provider,
    protocol,
    baseUrl,
    emptyApiKeyHosts,
  }) : null, [hasConnectionSchema, provider, protocol, baseUrl, emptyApiKeyHosts]);
  const connectionContractValues = useMemo(() => provider ? buildConnectionContractValues({
    connectionName: suggestedConnectionName,
    displayName: getProviderDisplayLabel(provider, language),
    providerId: provider.id,
    provider,
    protocol,
    baseUrl,
    apiKey,
    credentialField,
    models,
    enabled: true,
    emptyApiKeyHosts,
    baseUrlVisible: hasConnectionSchema ? undefined : Boolean(requirements?.showBaseUrl),
  }) : null, [
    apiKey,
    baseUrl,
    credentialField,
    emptyApiKeyHosts,
    hasConnectionSchema,
    language,
    models,
    protocol,
    provider,
    requirements?.showBaseUrl,
    suggestedConnectionName,
  ]);
  const connectionAuthority = evaluateConnectionSchemaAuthority(
    connectionContractValues ?? {},
    connectionFields,
  );
  const connectionFieldStates = connectionAuthority.states;
  const missingConnectionFields = connectionContractValues && hasConnectionSchema
    ? validateConnectionContractValues(connectionContractValues, connectionSchemaFields)
    : [];
  const fieldIsVisible = (key: string) => !hasConnectionSchema
    || connectionFieldStates[key]?.visible === true;
  const fieldCanWrite = (key: string) => isConnectionSchemaFieldWritable(connectionAuthority, key);
  const fieldIsReadOnly = (key: string) => !fieldCanWrite(key);
  const visibleApiKeyStates = hasConnectionSchema
    ? (['api_key', 'api_keys'] as ConnectionCredentialField[])
      .map((key) => ({ key, state: connectionFieldStates[key] }))
      .filter(({ state }) => state?.visible)
    : [];
  const writableCredentialFields = visibleApiKeyStates
    .filter(({ key }) => fieldCanWrite(key))
    .map(({ key }) => key);
  const showProviderField = fieldIsVisible('provider_id');
  const showProtocolField = hasConnectionSchema
    ? fieldIsVisible('protocol')
    : Boolean(requirements?.showProtocol);
  const showApiKeyField = hasConnectionSchema
    ? visibleApiKeyStates.length > 0
    : Boolean(requirements?.showApiKey);
  const apiKeyRequired = hasConnectionSchema
    ? visibleApiKeyStates.some(({ state }) => state?.required)
    : Boolean(requirements?.apiKeyRequired);
  const apiKeyIsReadOnly = hasConnectionSchema
    && writableCredentialFields.length === 0;
  const showBaseUrlField = hasConnectionSchema
    ? fieldIsVisible('base_url')
    : Boolean(requirements?.showBaseUrl);
  const showModelsField = fieldIsVisible('models');
  const modelsAreReadOnly = fieldIsReadOnly('models');
  const supportsDiscovery = provider?.supportsDiscovery === true;
  const canPersistConnectionIdentity = connectionAuthority.usable
    && fieldCanWrite('connection_name')
    && fieldCanWrite('provider_id');
  const discoveryEnabledByContract = hasConnectionSchema
    ? Boolean(
      canPersistConnectionIdentity
      && connectionContractValues
      && isConnectionModelDiscoveryEnabled(
        connectionContractValues,
        connectionSchemaFields,
      )
    )
    : !apiKeyRequired || Boolean(apiKey.trim());
  const cloudContractReady = Boolean(
    provider
    && canPersistConnectionIdentity
    && missingConnectionFields.length === 0,
  );
  const protocolOptions = useMemo(() => Array.from(
    new Map(providers.map((entry) => [entry.protocol, entry.protocol])).entries(),
  ).map(([value, label]) => ({ value, label })), [providers]);

  const clearConnectionTest = () => {
    connectionTestVersionRef.current += 1;
    setTestResult(null);
  };
  const clearConnectionEvidence = () => {
    clearConnectionTest();
    discoveryVersionRef.current += 1;
    setDiscoveredModels([]);
    setDiscoverNote(null);
  };

  // One model per Enter/click, but pasted comma/whitespace-separated lists are
  // split, trimmed and deduped in one pass.
  const addModelToken = (raw: string) => {
    if (modelsAreReadOnly) return;
    const tokens = raw.split(/[,\s]+/).map((token) => token.trim()).filter(Boolean);
    if (tokens.length === 0) return;
    setModels(Array.from(new Set([...modelOptions, ...tokens])).join(','));
    setModelDraft('');
    clearConnectionTest();
  };
  const removeModelToken = (model: string) => {
    if (modelsAreReadOnly) return;
    const removedRef = modelRefFor(model);
    setModels(modelOptions.filter((entry) => entry !== model).join(','));
    if (reportModel === model) {
      setReportModel('');
    }
    setFallbackModels((current) => parseModels(current)
      .filter((entry) => entry !== removedRef)
      .join(','));
    setVisionModel((current) => current === removedRef ? '' : current);
    clearConnectionTest();
  };

  const order = mode ? STEP_ORDER[mode] : STEP_ORDER.cloud;
  const stepIndex = order.indexOf(step);

  const applyProvider = (nextProviderId: string) => {
    const nextProvider = providers.find((entry) => entry.id === nextProviderId);
    if (!nextProvider) {
      return;
    }
    const nextProtocol = nextProvider.protocol ?? 'openai';
    const nextBaseUrl = nextProvider.defaultBaseUrl ?? '';
    const proposedAuthority = evaluateConnectionSchemaAuthority(buildConnectionContractValues({
      connectionName: suggestConnectionName(existingChannelNames, nextProvider.id),
      displayName: getProviderDisplayLabel(nextProvider, language),
      providerId: nextProvider.id,
      provider: nextProvider,
      protocol: nextProtocol,
      baseUrl: nextBaseUrl,
      apiKey,
      credentialField,
      models,
      enabled: true,
      emptyApiKeyHosts,
    }), connectionFields);
    const proposedStates = proposedAuthority.states;
    const proposedFieldCanWrite = (key: string) => (
      isConnectionSchemaFieldWritable(proposedAuthority, key)
    );
    if (!proposedFieldCanWrite('provider_id')) {
      return;
    }
    const canAdoptProviderDefault = (key: string) => !hasConnectionSchema
      || proposedStates[key] === undefined
      || proposedStates[key].visible === false
      || proposedFieldCanWrite(key);
    const proposedWritableCredentials = (['api_key', 'api_keys'] as ConnectionCredentialField[])
      .filter(proposedFieldCanWrite);
    const previousDraftRefs = new Set(modelOptions.map((model) => modelRefFor(model)));

    setProviderId(nextProviderId);
    if (canAdoptProviderDefault('protocol')) {
      setProtocol(nextProtocol);
    }
    if (canAdoptProviderDefault('base_url')) {
      setBaseUrl(nextBaseUrl);
    }
    if (!hasConnectionSchema || proposedWritableCredentials.length > 0) {
      setApiKey('');
      setCredentialField(proposedWritableCredentials[0] ?? 'api_key');
    }
    // Do not seed example model IDs: models come from discovery or manual entry.
    if (canAdoptProviderDefault('models')) {
      setModels('');
      setReportModel('');
      setFallbackModels((current) => parseModels(current)
        .filter((entry) => !previousDraftRefs.has(entry))
        .join(','));
      setVisionModel((current) => previousDraftRefs.has(current) ? '' : current);
    }
    clearConnectionEvidence();
  };

  const handleApiKeyChange = (nextValue: string) => {
    if (!hasConnectionSchema) {
      setApiKey(nextValue);
      clearConnectionEvidence();
      return;
    }
    const preferred: ConnectionCredentialField = parseModels(nextValue).length > 1
      ? 'api_keys'
      : 'api_key';
    const nextCredentialField = [preferred, credentialField, ...writableCredentialFields]
      .find((key, index, candidates) => (
        candidates.indexOf(key) === index
        && writableCredentialFields.includes(key)
      ));
    if (!nextCredentialField) {
      return;
    }
    setCredentialField(nextCredentialField);
    setApiKey(nextValue);
    clearConnectionEvidence();
  };

  const handleDiscover = async () => {
    if (
      !provider
      || !canPersistConnectionIdentity
      || !supportsDiscovery
      || !discoveryEnabledByContract
    ) {
      return;
    }
    setIsDiscovering(true);
    setDiscoverNote(null);
    const requestVersion = discoveryVersionRef.current + 1;
    discoveryVersionRef.current = requestVersion;
    try {
      const result = await systemConfigApi.discoverLLMChannelModels({
        name: suggestedConnectionName,
        providerId: provider.id,
        protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
      });
      if (discoveryVersionRef.current !== requestVersion) {
        return;
      }
      if (result.success && result.models.length > 0) {
        // Present the results for explicit confirmation — never enable all of
        // them automatically.
        setDiscoveredModels(result.models);
        setDiscoverNote({ ok: true, message: formatUiText(text.discovered, { count: result.models.length }) });
      } else {
        setDiscoverNote({ ok: false, message: text.noDiscovered });
      }
    } catch {
      if (discoveryVersionRef.current === requestVersion) {
        setDiscoverNote({ ok: false, message: text.discoveryFailed });
      }
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleTestConnection = async () => {
    if (!provider || (hasConnectionSchema && !cloudContractReady)) {
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    const requestVersion = connectionTestVersionRef.current + 1;
    connectionTestVersionRef.current = requestVersion;
    // Reuse the shared runner so the wizard surfaces the same actionable
    // diagnostics, resolved effective config, and capability results as the
    // Model Access editor instead of a binary pass/fail.
    const outcome = await runLlmConnectionCheck({
      name: suggestedConnectionName,
      providerId: provider.id,
      protocol,
      baseUrl: baseUrl.trim(),
      apiKey: apiKey.trim(),
      models: [
        effectivePrimaryModel,
        ...modelOptions.filter((model) => model !== effectivePrimaryModel),
      ].filter(Boolean),
      enabled: true,
      capabilityChecks: WIZARD_CAPABILITY_CHECKS,
    }, language);
    if (connectionTestVersionRef.current === requestVersion) {
      setTestResult(outcome);
    }
    setIsTesting(false);
  };

  const chooseMode = (nextMode: WizardMode) => {
    clearConnectionTest();
    setMode(nextMode);
    if (nextMode === 'cloud' && !baseUrl) {
      applyProvider(providerId);
    }
  };

  const canAdvance = (() => {
    switch (step) {
      case 'mode':
        return mode !== null;
      case 'connection': {
        if (mode === 'cli') {
          return Boolean(cliBackend);
        }
        if (hasConnectionSchema) {
          const stepFields = new Set([
            'connection_name',
            'display_name',
            'provider_id',
            'protocol',
            'base_url',
            'api_key',
            'api_keys',
            'enabled',
          ]);
          return Boolean(
            provider
            && canPersistConnectionIdentity
            && !missingConnectionFields.some((field) => stepFields.has(field)),
          );
        }
        // Official providers use their SDK default / prefilled endpoint, so Base
        // URL is never a blocker here; the API key is required unless the
        // provider is key-exempt (e.g. Ollama).
        const keyOk = !requirements?.apiKeyRequired || apiKey.trim().length > 0;
        const baseUrlOk = !requirements?.baseUrlRequired || baseUrl.trim().length > 0;
        return Boolean(provider && keyOk && baseUrlOk);
      }
      case 'models':
        return hasConnectionSchema
          ? canPersistConnectionIdentity
            && !missingConnectionFields.includes('models')
          : modelOptions.length > 0;
      case 'model':
        return !hasConnectionSchema || cloudContractReady;
      case 'local_model':
        return Boolean(localModelReady);
      default:
        return true;
    }
  })();

  const goNext = () => {
    if (!canAdvance) {
      return;
    }
    if (step === 'model' && !reportModel && modelOptions.length > 0) {
      setReportModel(modelOptions[0]);
    }
    const next = order[stepIndex + 1];
    if (next) {
      setStep(next);
    }
  };
  const goBack = () => {
    const prev = order[stepIndex - 1];
    if (prev) {
      setStep(prev);
    }
  };

  const handleSave = async () => {
    if (mode === 'local_model') {
      setSavedSummary({
        mode,
        execution: text.localModel,
        primaryModelRef: localModelReady ? `ollama/${localModelReady}` : '',
        fallbackModels: [],
        visionModel: '',
      });
      return;
    }
    if (mode === 'cloud' && hasConnectionSchema && !cloudContractReady) {
      return;
    }
    setSaveError(null);
    const result = await onComplete(buildItems());
    if (!result.success) {
      // Keep the modal open and surface the failure in place.
      setSaveError(result.error?.trim() || text.saveFailedMessage);
      return;
    }
    const normalizedFallbacks = parseModels(fallbackModels)
      .filter((entry) => entry !== effectivePrimaryModelRef);
    setSavedSummary({
      mode: mode ?? 'cloud',
      execution: mode === 'cli'
        ? CLI_BACKENDS.find((entry) => entry.value === cliBackend)?.label ?? text.localCli
        : text.cloudApi,
      primaryModelRef: mode === 'cloud' ? effectivePrimaryModelRef : '',
      fallbackModels: mode === 'cloud' ? normalizedFallbacks : [],
      visionModel: mode === 'cloud' ? visionModel : '',
    });
  };

  const buildItems = (): WizardDraftItem[] => {
    if (mode === 'local_model') {
      return [];
    }
    if (mode === 'cli') {
      return [{ key: 'GENERATION_BACKEND', value: cliBackend }];
    }
    if (!provider || (hasConnectionSchema && !cloudContractReady)) {
      return [];
    }
    const name = suggestedConnectionName;
    const up = name.toUpperCase();
    const primaryModelRef = effectivePrimaryModelRef;
    // Merge into any existing channels instead of replacing the whole list.
    const mergedChannels = Array.from(new Set([...existingChannelNames, name])).filter(Boolean).join(',');
    const items: WizardDraftItem[] = [
      // Make the configured channels the active source so a co-existing YAML /
      // Legacy config doesn't silently shadow the wizard result.
      { key: 'LLM_CONFIG_MODE', value: 'channels' },
      { key: 'GENERATION_BACKEND', value: 'litellm' },
      { key: 'LLM_CHANNELS', value: mergedChannels },
    ];
    const pushConnectionField = (field: string, suffix: string, value: string) => {
      if (!hasConnectionSchema || fieldCanWrite(field)) {
        items.push({ key: `LLM_${up}_${suffix}`, value });
      }
    };
    if (hasConnectionSchema) {
      pushConnectionField('display_name', 'DISPLAY_NAME', getProviderDisplayLabel(provider, language));
    }
    pushConnectionField('provider_id', 'PROVIDER', provider.id);
    pushConnectionField('protocol', 'PROTOCOL', protocol);
    pushConnectionField('models', 'MODELS', modelOptions.join(','));
    pushConnectionField('enabled', 'ENABLED', 'true');
    if (primaryModelRef) {
      items.push({ key: 'LITELLM_MODEL', value: primaryModelRef });
    }
    items.push({
      key: 'LITELLM_FALLBACK_MODELS',
      value: parseModels(fallbackModels)
        .filter((entry) => entry !== primaryModelRef)
        .join(','),
    });
    items.push({ key: 'VISION_MODEL', value: visionModel });
    // Base URL: official providers with a blank template endpoint use the SDK
    // default; only emit an explicit endpoint when one is provided.
    if (baseUrl.trim() && (!hasConnectionSchema || fieldCanWrite('base_url'))) {
      items.push({ key: `LLM_${up}_BASE_URL`, value: baseUrl.trim() });
    }
    // API key: omit for key-exempt local runtimes (e.g. Ollama).
    if (apiKey.trim()) {
      if (!hasConnectionSchema) {
        items.push({ key: `LLM_${up}_API_KEY`, value: apiKey.trim() });
      } else if (fieldCanWrite(credentialField)) {
        items.push({
          key: `LLM_${up}_${credentialField === 'api_keys' ? 'API_KEYS' : 'API_KEY'}`,
          value: apiKey.trim(),
        });
      }
    }
    return items;
  };

  const stepLabel = formatUiText(text.step, { current: stepIndex + 1, total: order.length });

  const capabilityRows = testResult?.capabilityResults
    ? WIZARD_CAPABILITY_CHECKS
      .map((capability) => ({ capability, result: testResult.capabilityResults?.[capability] }))
      .filter((row): row is { capability: LLMCapabilityCheck; result: LLMCapabilityCheckResult } => (
        Boolean(row.result)
      ))
    : [];
  const capabilityStatusLabel = (status: LLMCapabilityCheckResult['status']): string => (
    status === 'passed' ? text.capabilityPassed
      : status === 'failed' ? text.capabilityFailed
        : text.capabilitySkipped
  );
  const capabilityStatusClass = (status: LLMCapabilityCheckResult['status']): string => (
    status === 'passed' ? 'text-success'
      : status === 'failed' ? 'text-warning'
        : 'text-muted-text'
  );
  const capabilityHelpSummary = getSettingsHelpContent(
    'settings.llm_channel.capability_checks',
    undefined,
    language,
  )?.summary;
  const fallbackHelpSummary = getSettingsHelpContent(
    'settings.ai_model.LITELLM_FALLBACK_MODELS',
    undefined,
    language,
  )?.summary;
  const visionHelpSummary = getSettingsHelpContent(
    'settings.ai_model.VISION_MODEL',
    undefined,
    language,
  )?.summary;
  const routingLabel = (value: string): string => {
    const option = routingOptions.find((entry) => entry.value === value);
    if (option) {
      return option.sublabel ? `${option.label} · ${option.sublabel}` : option.label;
    }
    const decoded = decodeModelRef(value);
    return decoded ? `${decoded.runtimeRoute} · ${decoded.connectionId}` : value;
  };

  if (savedSummary) {
    return (
      <Modal isOpen onClose={onClose} title={text.title}>
        <div data-testid="first-run-wizard" className="space-y-5">
          <InlineAlert
            variant="success"
            title={text.savedTitle}
            message={savedSummary.mode === 'local_model'
              ? text.localSavedDescription
              : text.savedDescription}
          />
          <dl
            className="space-y-2 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 text-sm"
            data-testid="wizard-saved-routing"
          >
            <div className="flex justify-between gap-3">
              <dt className="text-muted-text">{text.execution}</dt>
              <dd className="font-medium text-foreground">{savedSummary.execution}</dd>
            </div>
            {savedSummary.mode !== 'cli' ? (
              <>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-text">
                    {savedSummary.mode === 'local_model' ? text.readyLocalModel : text.reportModel}
                  </dt>
                  <dd className="min-w-0 text-right font-medium text-foreground">
                    {routingLabel(savedSummary.primaryModelRef)}
                  </dd>
                </div>
                {savedSummary.mode === 'cloud' ? (
                  <>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-text">{text.fallbackModels}</dt>
                      <dd className="min-w-0 text-right font-medium text-foreground">
                        {savedSummary.fallbackModels.length > 0
                          ? savedSummary.fallbackModels.map(routingLabel).join(' -> ')
                          : text.none}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-text">{text.visionModel}</dt>
                      <dd className="min-w-0 text-right font-medium text-foreground">
                        {savedSummary.visionModel
                          ? routingLabel(savedSummary.visionModel)
                          : text.inheritPrimary}
                      </dd>
                    </div>
                  </>
                ) : null}
              </>
            ) : null}
          </dl>
          <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--settings-border)] pt-4">
            {savedSummary.mode === 'cloud' && onViewRouting ? (
              <Button type="button" variant="secondary" size="default" onClick={onViewRouting}>
                {text.viewRouting}
              </Button>
            ) : null}
            <Button
              type="button"
              variant={savedSummary.mode === 'local_model' && onStartFirstAnalysis ? 'secondary' : 'primary'}
              size="default"
              onClick={onClose}
            >
              {text.done}
            </Button>
            {savedSummary.mode === 'local_model' && onStartFirstAnalysis ? (
              <Button type="button" variant="primary" size="default" onClick={onStartFirstAnalysis}>
                {text.startFirstAnalysis}
              </Button>
            ) : null}
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={text.title}
      size={mode === 'local_model' && step === 'local_model' ? 'fullscreen' : 'default'}
    >
      <div data-testid="first-run-wizard" className="space-y-5">
        <p className="text-xs text-muted-text">{stepLabel}</p>

        {step === 'mode' ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              {text.chooseMode}
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {(['cloud', 'local_model', 'cli'] as WizardMode[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={mode === value}
                  onClick={() => chooseMode(value)}
                  className={`rounded-lg border px-4 py-3 text-left text-sm transition-colors ${
                    mode === value
                      ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-foreground'
                      : 'border-[var(--settings-border)] bg-[var(--settings-surface)] text-secondary-text hover:bg-[var(--settings-surface-hover)]'
                  }`}
                >
                  <span className="block font-medium text-foreground">
                    {value === 'cloud'
                      ? text.cloudApi
                      : value === 'local_model'
                        ? text.localModel
                        : text.localCli}
                  </span>
                  <span className="mt-1 block text-xs text-muted-text">
                    {value === 'cloud'
                      ? text.cloudDescription
                      : value === 'local_model'
                        ? text.localModelDescription
                        : text.cliDescription}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 'connection' && mode === 'cloud' ? (
          <form className="space-y-3" onSubmit={(event) => event.preventDefault()}>
            {showProviderField ? (
              <div>
                <label htmlFor="wizard-provider" className="mb-1 block text-sm text-foreground">
                  {text.provider}
                </label>
                <Select
                  id="wizard-provider"
                  value={providerId}
                  onChange={applyProvider}
                  options={providers.map((entry) => ({
                    value: entry.id,
                    label: getProviderDisplayLabel(entry, language),
                  }))}
                  disabled={fieldIsReadOnly('provider_id')}
                  className={SETTINGS_CONTROL_WIDTH_CLASS}
                />
              </div>
            ) : null}
            {showProtocolField ? (
              <div>
                <label htmlFor="wizard-protocol" className="mb-1 block text-sm text-foreground">
                  {text.protocol}
                </label>
                <Select
                  id="wizard-protocol"
                  value={protocol}
                  onChange={(nextProtocol) => {
                    if (!fieldIsReadOnly('protocol')) {
                      setProtocol(nextProtocol);
                      clearConnectionEvidence();
                    }
                  }}
                  options={protocolOptions}
                  disabled={fieldIsReadOnly('protocol')}
                  className={SETTINGS_CONTROL_WIDTH_CLASS}
                />
              </div>
            ) : null}
            {showApiKeyField ? (
              <div>
                <label htmlFor="wizard-api-key" className="mb-1 block text-sm text-foreground">
                  {apiKeyRequired
                    ? text.apiKey
                    : text.apiKeyOptional}
                </label>
                <CredentialInput
                  id="wizard-api-key"
                  purpose="provider-secret"
                  value={apiKey}
                  onChange={(event) => handleApiKeyChange(event.target.value)}
                  placeholder={apiKeyRequired
                    ? text.apiKeyPlaceholder
                    : text.localKeyPlaceholder}
                  disabled={apiKeyIsReadOnly}
                />
                <div className="mt-1">
                  <ProviderQuickLinks
                    provider={provider}
                    context="credentials"
                    language={language}
                    primaryLabel={apiKeyRequired ? text.apiKey : text.apiKeyOptional}
                    secondaryLabel={provider ? getProviderDisplayLabel(provider, language) : text.provider}
                  />
                </div>
              </div>
            ) : null}
            {showBaseUrlField ? (
              <div>
                <label htmlFor="wizard-base-url" className="mb-1 block text-sm text-foreground">
                  {text.baseUrl}
                </label>
                <Input
                  id="wizard-base-url"
                  value={baseUrl}
                  onChange={(event) => {
                    if (!fieldIsReadOnly('base_url')) {
                      setBaseUrl(event.target.value);
                      clearConnectionEvidence();
                    }
                  }}
                  disabled={fieldIsReadOnly('base_url')}
                  fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
                />
              </div>
            ) : null}
          </form>
        ) : null}

        {step !== 'mode' && mode === 'cloud' && !connectionAuthority.usable ? (
          <InlineAlert
            variant="warning"
            title={text.contractUnsupportedTitle}
            message={connectionAuthority.reason === 'unknown_condition'
              ? text.contractUnknownMessage
              : text.contractUnsupportedMessage}
          />
        ) : null}

        {step === 'connection' && mode === 'cli' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-cli" className="block text-sm text-foreground">
              {text.chooseCli}
            </label>
            <Select
              id="wizard-cli"
              value={cliBackend}
              onChange={setCliBackend}
              options={CLI_BACKENDS}
              placeholder={text.select}
              className={SETTINGS_CONTROL_WIDTH_CLASS}
            />
          </div>
        ) : null}

        {step === 'local_model' && mode === 'local_model' ? (
          <LocalModelsPanel
            language={language}
            headingAs="h3"
            onConfigurationChanged={onLocalModelConfigurationChanged}
            onModelReady={setLocalModelReady}
          />
        ) : null}

        {step === 'models' && showModelsField ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="block text-sm text-foreground">
                {text.availableModels}
              </span>
              {supportsDiscovery ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="compact"
                  onClick={() => void handleDiscover()}
                  disabled={
                    isDiscovering
                    || !canPersistConnectionIdentity
                    || !discoveryEnabledByContract
                  }
                  isLoading={isDiscovering}
                >
                  {text.discoverModels}
                </Button>
              ) : null}
            </div>
            <ProviderQuickLinks
              provider={provider}
              context="models"
              language={language}
              primaryLabel={text.availableModels}
              secondaryLabel={provider ? getProviderDisplayLabel(provider, language) : text.provider}
            />
            {!supportsDiscovery ? (
              <p className="text-xs text-muted-text">
                {text.discoveryUnsupported}
              </p>
            ) : null}
            {discoveredModels.length > 0 ? (
              <ModelMultiSelect
                options={discoveredModels}
                isSelected={(model) => modelOptions.includes(model)}
                onToggle={(model) => (modelOptions.includes(model) ? removeModelToken(model) : addModelToken(model))}
                disabled={modelsAreReadOnly}
                language={language}
              />
            ) : null}
            {modelOptions.length > 0 ? (
              <div className="flex flex-wrap gap-1.5" data-testid="wizard-model-chips">
                {modelOptions.map((model) => (
                  <span
                    key={model}
                    className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--settings-border)] bg-[var(--settings-surface)] px-1.5 py-0.5 text-xs text-secondary-text"
                  >
                    <span className="truncate">{model}</span>
                    <button
                      type="button"
                      aria-label={formatUiText(text.removeModel, { model })}
                      disabled={modelsAreReadOnly}
                      onClick={() => removeModelToken(model)}
                      className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted-text hover:text-danger"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-text">
                {text.noModels}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Input
                id="wizard-models"
                value={modelDraft}
                aria-label={text.addModel}
                placeholder={text.addModelPlaceholder}
                disabled={modelsAreReadOnly}
                onChange={(event) => setModelDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addModelToken(modelDraft);
                  }
                }}
                onPaste={(event) => {
                  const text = event.clipboardData.getData('text');
                  // A pasted list (comma/whitespace separated) becomes tokens
                  // immediately; a single id falls through to the normal input.
                  if (/[,\s]/.test(text.trim())) {
                    event.preventDefault();
                    addModelToken(`${modelDraft} ${text}`);
                  }
                }}
              />
              <Button
                type="button"
                variant="secondary"
                size="compact"
                className="shrink-0"
                disabled={modelsAreReadOnly || !modelDraft.trim()}
                onClick={() => addModelToken(modelDraft)}
              >
                {text.add}
              </Button>
            </div>
            {discoverNote ? (
              <p className={`text-xs ${discoverNote.ok ? 'text-success' : 'text-warning'}`}>{discoverNote.message}</p>
            ) : null}
            <p className="text-xs text-muted-text">
              {text.modelSourceHint}
            </p>
          </div>
        ) : null}

        {step === 'model' ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="wizard-report-model" className="block text-sm text-foreground">
                {text.reportModel}
              </label>
              <Select
                id="wizard-report-model"
                value={effectivePrimaryModel}
                onChange={(nextModel) => {
                  setReportModel(nextModel);
                  clearConnectionTest();
                  const nextPrimaryRef = modelRefFor(nextModel);
                  setFallbackModels((current) => parseModels(current)
                    .filter((entry) => entry !== nextPrimaryRef)
                    .join(','));
                }}
                options={modelOptions.map((model) => ({ value: model, label: model }))}
                className={SETTINGS_CONTROL_WIDTH_CLASS}
              />
              <p className="text-xs text-muted-text">
                {text.inheritanceHint}
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-foreground">{text.fallbackModels}</p>
              <ModelFallbackEditor
                value={fallbackModels}
                onChange={setFallbackModels}
                options={routingOptions}
                primaryRoute={effectivePrimaryModelRef}
                language={language}
              />
              {fallbackHelpSummary ? (
                <p className="text-xs text-muted-text">{fallbackHelpSummary}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <label htmlFor="wizard-vision-model" className="block text-sm text-foreground">
                {text.visionModel}
              </label>
              <Select
                id="wizard-vision-model"
                value={visionModel}
                onChange={setVisionModel}
                options={[
                  { value: '', label: text.inheritPrimary },
                  ...routingOptions.map((option) => ({
                    value: option.value,
                    label: option.sublabel ? `${option.label} · ${option.sublabel}` : option.label,
                  })),
                ]}
                className={SETTINGS_CONTROL_WIDTH_CLASS}
              />
              {visionHelpSummary ? (
                <p className="text-xs text-muted-text">{visionHelpSummary}</p>
              ) : null}
            </div>
          </div>
        ) : null}

        {step === 'review' ? (
          <div className="space-y-3">
            <InlineAlert
              variant="info"
              message={mode === 'local_model'
                ? formatUiText(text.localReviewDescription, { model: localModelReady })
                : text.reviewDescription}
            />
            {/* User-facing summary only — no internal keys such as LLM_CHANNELS. */}
            <dl className="space-y-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-text">{text.execution}</dt>
                <dd className="font-medium text-foreground">
                  {mode === 'cli'
                    ? CLI_BACKENDS.find((entry) => entry.value === cliBackend)?.label ?? text.localCli
                    : mode === 'local_model'
                      ? text.localModel
                      : text.cloudApi}
                </dd>
              </div>
              {mode === 'cloud' ? (
                <>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.modelService}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">
                      {provider ? getProviderDisplayLabel(provider, language) : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.availableModels}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">
                      {formatUiText(text.modelCount, { count: modelOptions.length })}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.reportModel}</dt>
                    <dd className="min-w-0 text-right font-medium text-foreground">
                      {effectivePrimaryModelRef ? routingLabel(effectivePrimaryModelRef) : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.fallbackModels}</dt>
                    <dd className="min-w-0 text-right font-medium text-foreground">
                      {parseModels(fallbackModels).length > 0
                        ? parseModels(fallbackModels).map(routingLabel).join(' -> ')
                        : text.none}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.visionModel}</dt>
                    <dd className="min-w-0 text-right font-medium text-foreground">
                      {visionModel ? routingLabel(visionModel) : text.inheritPrimary}
                    </dd>
                  </div>
                </>
              ) : null}
              {mode === 'local_model' ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-text">{text.readyLocalModel}</dt>
                  <dd className="min-w-0 text-right font-medium text-foreground">
                    {localModelReady}
                  </dd>
                </div>
              ) : null}
            </dl>
            {saveError ? <InlineAlert variant="danger" title={text.saveFailedTitle} message={saveError} /> : null}
            {mode === 'cloud' ? (
              <div className="space-y-1.5">
                <Button
                  type="button"
                  variant="secondary"
                  size="compact"
                  onClick={() => void handleTestConnection()}
                  disabled={isTesting || (hasConnectionSchema && !cloudContractReady)}
                  isLoading={isTesting}
                >
                  {text.testOptional}
                </Button>
                <p className="text-xs text-muted-text">
                  {text.testHint}
                </p>
                {testResult ? (
                  <div className="space-y-1.5" data-testid="wizard-test-result">
                    <p className={`text-xs ${testResult.status === 'success' ? 'text-success' : 'text-danger'}`}>
                      {testResult.text}
                    </p>
                    {testResult.hint ? (
                      <p className="text-xs text-secondary-text">{testResult.hint}</p>
                    ) : null}
                    {testResult.resolvedModel ? (
                      <p className="text-xs text-muted-text" data-testid="wizard-resolved-config">
                        {formatUiText(text.resolvedConfig, {
                          value: `${testResult.resolvedModel}${testResult.resolvedProtocol ? ` · ${testResult.resolvedProtocol}` : ''}`,
                        })}
                      </p>
                    ) : null}
                    {capabilityRows.length > 0 ? (
                      <div className="space-y-1" data-testid="wizard-capability-results">
                        <p className="text-xs font-medium text-foreground">{text.capabilityTitle}</p>
                        <ul className="space-y-0.5">
                          {capabilityRows.map(({ capability, result }) => (
                            <li key={capability} className="flex items-baseline justify-between gap-2 text-xs">
                              <span className="min-w-0 truncate text-secondary-text">
                                {getLlmCapabilityLabel(capability, language)}
                              </span>
                              <span className={`shrink-0 font-medium ${capabilityStatusClass(result.status)}`}>
                                {capabilityStatusLabel(result.status)}
                              </span>
                            </li>
                          ))}
                        </ul>
                        {capabilityHelpSummary ? (
                          <p className="text-xs text-muted-text">{capabilityHelpSummary}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-2 border-t border-[var(--settings-border)] pt-4">
          <Button type="button" variant="secondary" size="default" onClick={onClose}>
            {text.cancel}
          </Button>
          <div className="flex items-center gap-2">
            {stepIndex > 0 ? (
              <Button type="button" variant="secondary" size="default" onClick={goBack} disabled={isSaving}>
                {text.back}
              </Button>
            ) : null}
            {step === 'review' ? (
              <Button
                type="button"
                variant="primary"
                size="default"
                onClick={() => void handleSave()}
                disabled={isSaving || (mode === 'cloud' && hasConnectionSchema && !cloudContractReady)}
                isLoading={isSaving}
              >
                {mode === 'local_model' ? text.completeSetup : text.saveApply}
              </Button>
            ) : (
              <Button
                type="button"
                variant="primary"
                size="default"
                onClick={goNext}
                disabled={!canAdvance}
              >
                {text.next}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
