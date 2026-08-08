import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { ConfirmDialog, InlineAlert, SearchInput, StatusDot } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import {
  MODEL_ACCESS_EDITOR_TEXT,
  MODEL_ACCESS_TEXT,
  localizeModelAccessIssue,
} from '../../locales/settingsModelAccess';
import { localModelsApi } from '../../api/localModels';
import { systemConfigApi } from '../../api/systemConfig';
import type { GenerationBackendStatusResponse } from '../../types/systemConfig';
import type { LocalModelRuntimeState } from '../../types/localModels';
import { inspectConnectionSchemaDefinition, getProviderDisplayLabel } from './llmConnectionContract';
import {
  parseModelAccessFieldKey,
  type ChannelFieldSuffix,
} from '../../utils/modelAccessFieldKey';
import { isModelRef } from '../../utils/modelRef';
import { getUiListSeparator } from '../../utils/uiLocale';
import ConnectionCard from './LLMConnectionCard';
import ConnectionModal from './LLMConnectionModal';
import {
  applyChannelDraftItems,
  buildChannelDraftItems,
  buildItemSourceByKey,
  channelConnectionNameCanWrite,
  channelFieldCanWrite,
  channelIdentityCanWrite,
  channelSchemaAllowsKnownOperations,
  channelsAreEqual,
  collectChannelRouteSet,
  findCatalogProvider,
  getChannelCompletenessIssues,
  getChannelDisplayNameIssues,
  getChannelNameIssues,
  getChannelSaveIssues,
  hasRuntimeOnlyMaskedHermesSecret,
  modelIdentityForConnection,
  normalizeTaskReferenceRoute,
  parseChannelsFromItems,
  parseRuntimeConfigFromItems,
  resolveChannelRouteModels,
  runChannelConnectionTest,
  shouldUseSavedHermesSecret,
  type ChannelConfig,
  type ChannelTestState,
  type LLMChannelEditorProps,
  type ModelReferenceReplacement,
} from './llmChannelEditorModel';

export type {
  ModelReferenceReplacement,
  TaskModelReference,
} from './llmChannelEditorModel';



export const LLMChannelEditor: React.FC<LLMChannelEditorProps> = ({
  items,
  providers,
  connectionFields,
  emptyApiKeyHosts = [],
  availableModelRoutes = [],
  availableModels = [],
  maskToken,
  persistedDraftItems,
  onDraftItemsChange,
  onValidityChange,
  resetSignal = 0,
  addSignal = 0,
  focusFieldRequest = null,
  disabled = false,
  catalogLoading = false,
  catalogUnavailable = false,
  onReloadCatalog,
  overriddenByMode = null,
  onViewDiagnostics,
  taskModelRefs = [],
  onManageModels,
  onReplaceModelReferences,
}) => {
  const { language } = useUiLanguage();
  const editorText = MODEL_ACCESS_EDITOR_TEXT[language];
  const initialItemSourceByKey = useMemo(() => buildItemSourceByKey(items), [items]);
  const initialChannels = useMemo(
    () => parseChannelsFromItems(items, initialItemSourceByKey, providers, connectionFields),
    [items, initialItemSourceByKey, providers, connectionFields],
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
    () => parseChannelsFromItems(
      hydratedItems,
      buildItemSourceByKey(hydratedItems),
      providers,
      connectionFields,
    ),
    [hydratedItems, providers, connectionFields],
  );

  const [channels, setChannels] = useState<ChannelConfig[]>(hydratedChannels);
  const [testStates, setTestStates] = useState<Record<string, ChannelTestState>>({});
  const [modal, setModal] = useState<null | { mode: 'add' } | { mode: 'edit'; index: number; focusModels?: boolean; focusField?: ChannelFieldSuffix }>(null);
  const [pendingRemove, setPendingRemove] = useState<{ index: number; name: string; referencedBy: string[] } | null>(null);
  const addChannelIdRef = useRef(0);
  const testNonceRef = useRef<Record<string, number>>({});
  const testRequestIdRef = useRef(0);
  const lastDraftFingerprintRef = useRef<string | null>(null);
  const onValidityChangeRef = useRef(onValidityChange);
  const [sourceFilter, setSourceFilter] = useState('');
  const [localRuntime, setLocalRuntime] = useState<LocalModelRuntimeState | null>(null);
  const [localRuntimeStatus, setLocalRuntimeStatus] = useState<'idle' | 'loading' | 'error'>('loading');
  const [cliStatus, setCliStatus] = useState<GenerationBackendStatusResponse | null>(null);
  const [cliStatusState, setCliStatusState] = useState<'idle' | 'loading' | 'error'>('loading');

  const connectionSchemaDefinition = useMemo(
    () => inspectConnectionSchemaDefinition(connectionFields),
    [connectionFields],
  );
  const schemaUnavailable = connectionSchemaDefinition.mode === 'schema'
    && !connectionSchemaDefinition.usable;
  const baseBusy = disabled
    || catalogLoading
    || catalogUnavailable
    || Boolean(overriddenByMode);
  const schemaAllowsInspection = connectionSchemaDefinition.reason === 'unknown_condition';
  const busy = baseBusy || (schemaUnavailable && !schemaAllowsInspection);
  const mutationBusy = baseBusy || schemaUnavailable;
  const knownEditorRouteSet = useMemo(() => new Set([
    ...availableModelRoutes,
    ...collectChannelRouteSet(channels, false),
  ]), [availableModelRoutes, channels]);
  const resolvedTaskModelRefs = useMemo(
    () => taskModelRefs.map((reference) => ({
      ...reference,
      route: normalizeTaskReferenceRoute(reference, knownEditorRouteSet),
    })),
    [knownEditorRouteSet, taskModelRefs],
  );

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

  // The page-level "Add model service" button lives in the parent header; it bumps
  // addSignal to open the add dialog here (same adjust-during-render pattern).
  const [prevAddSignal, setPrevAddSignal] = useState(addSignal);
  if (prevAddSignal !== addSignal) {
    setPrevAddSignal(addSignal);
    if (!mutationBusy) {
      setModal({ mode: 'add' });
    }
  }

  const [handledFocusRequestId, setHandledFocusRequestId] = useState<number | null>(null);
  if (focusFieldRequest && handledFocusRequestId !== focusFieldRequest.requestId && !busy) {
    const parsed = parseModelAccessFieldKey(focusFieldRequest.key);
    const index = parsed
      ? channels.findIndex((channel) => channel.name === parsed.connectionName)
      : -1;
    if (
      parsed
      && index >= 0
      && (schemaAllowsInspection || channelSchemaAllowsKnownOperations(
        channels[index],
        providers,
        emptyApiKeyHosts,
        connectionFields,
      ))
    ) {
      setHandledFocusRequestId(focusFieldRequest.requestId);
      setPendingRemove(null);
      setModal({ mode: 'edit', index, focusField: parsed.suffix });
    }
  }

  useEffect(() => {
    let cancelled = false;
    void localModelsApi.getRuntime()
      .then((runtime) => {
        if (cancelled) return;
        setLocalRuntime(runtime);
        setLocalRuntimeStatus('idle');
      })
      .catch(() => {
        if (cancelled) return;
        setLocalRuntime(null);
        setLocalRuntimeStatus('error');
      });
    void systemConfigApi.getGenerationBackendStatus()
      .then((status) => {
        if (cancelled) return;
        setCliStatus(status);
        setCliStatusState('idle');
      })
      .catch(() => {
        if (cancelled) return;
        setCliStatus(null);
        setCliStatusState('error');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasChanges = useMemo(() => {
    if (channels.length !== initialChannels.length) {
      return true;
    }
    return channels.some((channel, index) => !channelsAreEqual(channel, initialChannels[index]));
  }, [channels, initialChannels]);

  // Structural gate: names must be valid for every channel and every enabled
  // channel must be complete before the draft can be saved.
  const blockingChannels = useMemo(
    () => catalogLoading ? [] : channels
      .map((channel, index) => ({
        channel,
        index,
        issues: getChannelSaveIssues(
          channel,
          providers,
          emptyApiKeyHosts,
          connectionFields,
          catalogUnavailable,
        ),
      }))
      .filter((entry) => entry.issues.length > 0),
    [catalogLoading, channels, providers, emptyApiKeyHosts, connectionFields, catalogUnavailable],
  );
  const draftValid = !catalogLoading
    && !catalogUnavailable
    && connectionSchemaDefinition.usable
    && blockingChannels.length === 0;

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
    providers,
    emptyApiKeyHosts,
    connectionFields,
  }), [
    channels,
    hasChanges,
    initialChannels,
    initialItemSourceByKey,
    initialNames,
    initialRuntimeConfig,
    providers,
    emptyApiKeyHosts,
    connectionFields,
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

  const openChannelEditor = (
    index: number,
    options: { focusModels?: boolean; focusField?: ChannelFieldSuffix } = {},
  ) => {
    const channel = channels[index];
    if (
      !channel
      || busy
      || (!schemaAllowsInspection && !channelSchemaAllowsKnownOperations(
        channel,
        providers,
        emptyApiKeyHosts,
        connectionFields,
      ))
    ) {
      return;
    }
    setModal({ mode: 'edit', index, ...options });
  };

  const handleTest = async (channel: ChannelConfig) => {
    if (
      mutationBusy
      || !channelSchemaAllowsKnownOperations(
        channel,
        providers,
        emptyApiKeyHosts,
        connectionFields,
      )
    ) {
      return;
    }
    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hermesSecretPersisted)) {
      setTestStates((previous) => ({
        ...previous,
        [channel.id]: { status: 'error', text: MODEL_ACCESS_TEXT[language].runtimeSecret },
      }));
      return;
    }
    const requestId = testRequestIdRef.current + 1;
    testRequestIdRef.current = requestId;
    testNonceRef.current[channel.id] = requestId;
    setTestStates((previous) => ({
      ...previous,
      [channel.id]: { status: 'loading', text: editorText.testing },
    }));
    const result = await runChannelConnectionTest(
      channel,
      shouldUseSavedHermesSecret(channel, maskToken, hermesSecretPersisted),
      language,
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
    const channel = channels[index];
    if (
      !channel
      || mutationBusy
      || !channelConnectionNameCanWrite(
        channel,
        providers,
        emptyApiKeyHosts,
        connectionFields,
      )
    ) {
      return;
    }
    const removedChannelId = channel.id;
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
    if (
      !channel
      || mutationBusy
      || !channelConnectionNameCanWrite(
        channel,
        providers,
        emptyApiKeyHosts,
        connectionFields,
      )
    ) {
      return;
    }
    const routes = channel.enabled
      ? new Set(resolveChannelRouteModels(channel))
      : new Set<string>();
    const modelRefs = new Set(Array.from(routes).map((route) => (
      modelIdentityForConnection(availableModels, channel.name, route)
    )));
    const referencedBy = Array.from(new Set(
      resolvedTaskModelRefs
        .filter((ref) => modelRefs.has(ref.route) || (!isModelRef(ref.route) && routes.has(ref.route)))
        .map((ref) => ref.label),
    ));
    setPendingRemove({ index, name: channel.displayName.trim() || channel.name || `#${index + 1}`, referencedBy });
  };

  // Enabling an incomplete connection opens the edit dialog instead of letting
  // an unusable connection go live.
  const toggleEnabled = (index: number) => {
    const channel = channels[index];
    if (
      !channel
      || mutationBusy
      || !channelFieldCanWrite(
        channel,
        'enabled',
        providers,
        emptyApiKeyHosts,
        connectionFields,
      )
    ) {
      return;
    }
    if (!channel.enabled) {
      const enabledChannel = { ...channel, enabled: true };
      const issues = [
        ...getChannelNameIssues(enabledChannel),
        ...getChannelCompletenessIssues(
          enabledChannel,
          providers,
          emptyApiKeyHosts,
          connectionFields,
          catalogUnavailable,
        ),
      ];
      if (issues.length > 0) {
        setModal({ mode: 'edit', index });
        return;
      }
    }
    setChannels((previous) => previous.map((item, rowIndex) => (
      rowIndex === index
        ? { ...item, enabled: !item.enabled, enabledValuePresent: true }
        : item
    )));
  };

  const handleModalSubmit = (
    channel: ChannelConfig,
    replacements: ModelReferenceReplacement[],
  ) => {
    if (
      !modal
      || mutationBusy
      || !channelSchemaAllowsKnownOperations(
        channel,
        providers,
        emptyApiKeyHosts,
        connectionFields,
      )
      || (
        modal.mode === 'add'
        && !channelIdentityCanWrite(
          channel,
          providers,
          emptyApiKeyHosts,
          connectionFields,
        )
      )
    ) {
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
          || previousChannel.providerId !== channel.providerId
          || previousChannel.protocol !== channel.protocol
          || previousChannel.baseUrl !== channel.baseUrl
          || previousChannel.apiKey !== channel.apiKey
          || previousChannel.credentialField !== channel.credentialField
          || previousChannel.models !== channel.models
          || previousChannel.extraHeaders !== channel.extraHeaders;
        if (connectionChanged) {
          clearTestState(previousChannel.id);
        }
      }
    }
    if (replacements.length > 0) {
      onReplaceModelReferences?.(replacements);
    }
    setModal(null);
  };

  const normalizedFilter = sourceFilter.trim().toLowerCase();
  const channelMatchesFilter = (channel: ChannelConfig) => {
    if (!normalizedFilter) {
      return true;
    }
    const provider = findCatalogProvider(providers, channel.providerId);
    const providerLabel = provider
      ? getProviderDisplayLabel(provider, language)
      : channel.providerId;
    const haystack = [
      channel.name,
      channel.displayName,
      channel.providerId,
      providerLabel,
      channel.models,
      channel.baseUrl,
      ...(channel.enabled ? resolvedTaskModelRefs
        .filter((ref) => {
          const routes = resolveChannelRouteModels(channel);
          return routes.includes(ref.route);
        })
        .map((ref) => ref.label) : []),
    ].join(' ').toLowerCase();
    return haystack.includes(normalizedFilter);
  };
  const filteredChannels = channels.filter(channelMatchesFilter);
  const primaryModel = initialRuntimeConfig.primaryModel.trim();
  const fallbackModels = initialRuntimeConfig.fallbackModels;
  const fallbackMatches = !normalizedFilter
    || primaryModel.toLowerCase().includes(normalizedFilter)
    || fallbackModels.some((model) => model.toLowerCase().includes(normalizedFilter))
    || editorText.hubFallbackGroup.toLowerCase().includes(normalizedFilter)
    || resolvedTaskModelRefs.some((ref) => (
      ref.route
      && (
        ref.route === primaryModel
        || fallbackModels.includes(ref.route)
        || ref.label.toLowerCase().includes(normalizedFilter)
      )
    ));
  const localMatches = !normalizedFilter
    || editorText.hubLocalGroup.toLowerCase().includes(normalizedFilter)
    || 'ollama'.includes(normalizedFilter)
    || (localRuntime?.configuration.primaryModel || '').toLowerCase().includes(normalizedFilter)
    || (localRuntime?.configuration.agentModel || '').toLowerCase().includes(normalizedFilter)
    || (localRuntime?.status || '').toLowerCase().includes(normalizedFilter);
  const cliMatches = !normalizedFilter
    || editorText.hubCliGroup.toLowerCase().includes(normalizedFilter)
    || 'cli'.includes(normalizedFilter)
    || (cliStatus?.primary?.backendId || '').toLowerCase().includes(normalizedFilter)
    || (cliStatus?.fallback?.backendId || '').toLowerCase().includes(normalizedFilter)
    || (cliStatus?.primary?.backendType || '').toLowerCase().includes(normalizedFilter);
  const hasAnyMatch = filteredChannels.length > 0 || localMatches || cliMatches || fallbackMatches;
  const localConfig = localRuntime?.configuration;
  const registeredCount = localConfig?.registeredModels?.length ?? 0;
  const localPrimary = (localConfig?.primaryModel || '').trim();
  const localAgent = (localConfig?.agentModel || '').trim();
  const localRuntimeLabel = localRuntime?.status || 'unknown';
  const cliPrimary = cliStatus?.primary;
  const cliIsLocal = cliPrimary?.backendType === 'local_cli';

  return (
    <div className="space-y-4" data-testid={modal ? 'model-sources-hub-wizard' : 'model-sources-hub'}>
      {modal ? (
        <ConnectionModal
          mode={modal.mode}
          initialChannel={modal.mode === 'edit' ? channels[modal.index] ?? null : null}
          focusModels={modal.mode === 'edit' ? modal.focusModels : false}
          focusField={modal.mode === 'edit' ? modal.focusField : undefined}
          channels={channels}
          availableModelRoutes={availableModelRoutes}
          availableModels={availableModels}
          providers={providers}
          connectionFields={connectionFields}
          emptyApiKeyHosts={emptyApiKeyHosts}
          maskToken={maskToken}
          hermesSecretPersisted={hermesSecretPersisted}
          catalogUnavailable={catalogUnavailable}
          disabled={busy}
          taskModelRefs={resolvedTaskModelRefs}
          onReloadCatalog={onReloadCatalog}
          onManageModels={onManageModels}
          canReplaceModelReferences={Boolean(onReplaceModelReferences)}
          onSubmit={handleModalSubmit}
          onClose={() => setModal(null)}
        />
      ) : null}
      <div
        className={modal ? 'hidden' : 'space-y-4'}
        aria-hidden={modal ? true : undefined}
        data-testid="model-sources-hub-body"
      >
      {overriddenByMode ? (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-2.5 text-xs text-secondary-text">
          <span>{editorText.readonly}</span>
          {onViewDiagnostics ? (
            <button
              type="button"
              className="settings-accent-text inline-flex min-h-11 min-w-11 items-center underline-offset-2 hover:underline"
              onClick={onViewDiagnostics}
            >
              {editorText.viewDetails}
            </button>
          ) : null}
        </div>
      ) : null}

      {catalogUnavailable ? (
        <div className="flex items-center gap-2 px-1 text-xs text-danger">
          <span>{editorText.catalogFailed}</span>
          {onReloadCatalog ? (
            <button type="button" className="inline-flex min-h-11 min-w-11 items-center underline underline-offset-2" onClick={onReloadCatalog}>
              {editorText.retry}
            </button>
          ) : null}
        </div>
      ) : null}

      {schemaUnavailable ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={editorText.schemaUnavailableTitle}
          message={editorText.schemaUnavailableMessage}
        />
      ) : null}

      <div className="space-y-2">
        <label htmlFor="model-sources-filter" className="sr-only">
          {editorText.hubSearchLabel}
        </label>
        <SearchInput
          id="model-sources-filter"
          value={sourceFilter}
          onChange={(event) => setSourceFilter(event.target.value)}
          placeholder={editorText.hubSearchPlaceholder}
          aria-label={editorText.hubSearchLabel}
          data-testid="model-sources-filter"
        />
      </div>

      {!hasAnyMatch ? (
        <p className="px-1 text-sm text-muted-text" data-testid="model-sources-no-matches">
          {editorText.hubNoSearchMatches}
        </p>
      ) : null}

      {fallbackMatches ? (
        <section
          className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
          data-testid="model-sources-fallback-group"
          aria-labelledby="model-sources-fallback-heading"
        >
          <h3 id="model-sources-fallback-heading" className="text-sm font-semibold text-foreground">
            {editorText.hubFallbackGroup}
          </h3>
          <p className="text-xs text-secondary-text">
            {primaryModel
              ? formatUiText(editorText.hubPrimaryModel, { model: primaryModel })
              : formatUiText(editorText.hubPrimaryModel, { model: MODEL_ACCESS_TEXT[language].disabled })}
          </p>
          <p className="text-xs text-secondary-text">
            {fallbackModels.length > 0
              ? formatUiText(editorText.hubFallbackOrder, {
                models: fallbackModels.join(getUiListSeparator(language)),
              })
              : editorText.hubFallbackNone}
          </p>
          <p className="text-xs text-muted-text">{editorText.hubFallbackEditHint}</p>
        </section>
      ) : null}

      <section
        className="space-y-2"
        data-testid="model-sources-cloud-group"
        aria-labelledby="model-sources-cloud-heading"
      >
        <h3 id="model-sources-cloud-heading" className="text-sm font-semibold text-foreground">
          {editorText.hubCloudGroup}
        </h3>
        {channels.length === 0 ? (
          <div className="settings-surface-overlay-muted rounded-xl border border-dashed settings-border-strong px-4 py-10 text-center">
            <p className="text-sm font-medium text-secondary-text">{editorText.emptyTitle}</p>
            <p className="mt-1 text-xs text-muted-text">{editorText.emptyDescription}</p>
          </div>
        ) : filteredChannels.length === 0 ? (
          normalizedFilter ? null : (
            <p className="text-xs text-muted-text">{editorText.hubCloudEmpty}</p>
          )
        ) : (
          <div className="space-y-2">
            {filteredChannels.map((channel) => {
              const index = channels.findIndex((entry) => entry.id === channel.id);
              if (index < 0) {
                return null;
              }
              return (
                <ConnectionCard
                  key={channel.id}
                  channel={channel}
                  providers={providers}
                  availableModels={availableModels}
                  taskModelRefs={resolvedTaskModelRefs}
                  unsaved={isChannelUnsaved(channel)}
                  busy={busy || (
                    !schemaAllowsInspection
                    && !channelSchemaAllowsKnownOperations(
                      channel,
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                    )
                  )}
                  testState={testStates[channel.id]}
                  issues={catalogLoading ? [] : [
                    ...getChannelNameIssues(channel),
                    ...getChannelDisplayNameIssues(channel, connectionFields),
                    ...getChannelCompletenessIssues(
                      channel,
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                      catalogUnavailable,
                    ),
                  ]}
                  onTest={() => void handleTest(channel)}
                  canTest={
                    !mutationBusy
                    && channelSchemaAllowsKnownOperations(
                      channel,
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                    )
                  }
                  onEdit={() => openChannelEditor(index)}
                  onManageModels={() => openChannelEditor(index, { focusModels: true })}
                  onToggleEnabled={() => toggleEnabled(index)}
                  canToggleEnabled={
                    !mutationBusy
                    && channelFieldCanWrite(
                      channel,
                      'enabled',
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                    )
                  }
                  onRemove={() => requestRemoveChannel(index)}
                  canRemove={
                    !mutationBusy
                    && channelConnectionNameCanWrite(
                      channel,
                      providers,
                      emptyApiKeyHosts,
                      connectionFields,
                    )
                  }
                />
              );
            })}
          </div>
        )}
      </section>

      {localMatches ? (
        <section
          className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
          data-testid="model-sources-local-group"
          aria-labelledby="model-sources-local-heading"
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusDot
              tone={
                localRuntimeStatus === 'error'
                  ? 'danger'
                  : localRuntime?.status === 'running'
                    ? 'success'
                    : localRuntime?.status === 'starting'
                      ? 'warning'
                      : 'neutral'
              }
              pulse={localRuntime?.status === 'starting'}
            />
            <h3 id="model-sources-local-heading" className="text-sm font-semibold text-foreground">
              {editorText.hubLocalGroup}
            </h3>
          </div>
          {localRuntimeStatus === 'loading' && !localRuntime ? (
            <p className="text-xs text-muted-text">{editorText.hubLocalLoading}</p>
          ) : localRuntimeStatus === 'error' ? (
            <p className="text-xs text-danger">{editorText.hubLocalFailed}</p>
          ) : (
            <div className="space-y-1 text-xs text-secondary-text">
              <p>{formatUiText(editorText.hubLocalRuntime, { status: localRuntimeLabel })}</p>
              {registeredCount > 0 ? (
                <p>{editorText.hubLocalConfigured} · {registeredCount}</p>
              ) : (
                <p>{editorText.hubLocalNone}</p>
              )}
              {localPrimary ? (
                <p>{formatUiText(editorText.hubLocalPrimary, { model: localPrimary })}</p>
              ) : null}
              {localAgent ? (
                <p>{formatUiText(editorText.hubLocalAgent, { model: localAgent })}</p>
              ) : null}
            </div>
          )}
        </section>
      ) : null}

      {cliMatches ? (
        <section
          className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
          data-testid="model-sources-cli-group"
          aria-labelledby="model-sources-cli-heading"
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusDot
              tone={
                cliStatusState === 'error'
                  ? 'danger'
                  : cliPrimary?.healthStatus === 'passed' || cliPrimary?.available
                    ? 'success'
                    : cliPrimary?.healthStatus === 'failed'
                      ? 'warning'
                      : 'neutral'
              }
            />
            <h3 id="model-sources-cli-heading" className="text-sm font-semibold text-foreground">
              {editorText.hubCliGroup}
            </h3>
          </div>
          {cliStatusState === 'loading' && !cliStatus ? (
            <p className="text-xs text-muted-text">{editorText.hubCliLoading}</p>
          ) : cliStatusState === 'error' ? (
            <p className="text-xs text-danger">{editorText.hubCliFailed}</p>
          ) : cliIsLocal && cliPrimary ? (
            <div className="space-y-1 text-xs text-secondary-text">
              <p>{formatUiText(editorText.hubCliPrimary, { backend: cliPrimary.backendId })}</p>
              {cliStatus?.fallback?.backendId ? (
                <p>{formatUiText(editorText.hubCliFallback, { backend: cliStatus.fallback.backendId })}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-secondary-text">{editorText.hubCliNone}</p>
          )}
        </section>
      ) : null}

      {!draftValid ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={editorText.invalidTitle}
          message={(
            <>
              <p className="mb-1">{editorText.invalidDescription}</p>
              <ul className="ml-4 list-disc space-y-0.5">
                {blockingChannels.map(({ channel, index, issues }) => (
                  <li key={channel.id || index}>
                    {formatUiText(editorText.invalidConnection, {
                      name: channel.displayName.trim() || channel.name || formatUiText(editorText.connectionNumber, { number: index + 1 }),
                      issues: issues.map((issue) => localizeModelAccessIssue(issue, language)).join(getUiListSeparator(language)),
                    })}
                  </li>
                ))}
              </ul>
            </>
          )}
        />
      ) : null}

      {onManageModels && channels.some((channel) => channel.enabled) ? (
        <div className="flex items-center justify-end px-1">
          <button
            type="button"
            className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
            onClick={onManageModels}
          >
            {editorText.assignModels}
          </button>
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={pendingRemove !== null}
        title={pendingRemove && pendingRemove.referencedBy.length > 0 ? editorText.cannotDeleteConnection : editorText.deleteConnectionTitle}
        message={pendingRemove
          ? (pendingRemove.referencedBy.length > 0
            ? formatUiText(editorText.referencedConnection, { name: pendingRemove.name, tasks: pendingRemove.referencedBy.join(getUiListSeparator(language)) })
            : formatUiText(editorText.removeDraftConnection, { name: pendingRemove.name }))
          : ''}
        confirmText={pendingRemove && pendingRemove.referencedBy.length > 0 ? editorText.replaceInRouting : MODEL_ACCESS_TEXT[language].deleteConnection}
        cancelText={MODEL_ACCESS_TEXT[language].cancel}
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
      </div>
    </div>
  );
};

