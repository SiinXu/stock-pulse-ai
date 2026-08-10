import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { useSearchParams } from 'react-router-dom';
import { systemConfigApi } from '../../api/systemConfig';
import { ConfirmDialog, InlineAlert, SearchInput, StatusDot } from '../common';
import { getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { UI_LANGUAGE_METADATA } from '../../i18n/uiLanguages';
import {
  MODEL_ACCESS_EDITOR_TEXT,
  MODEL_ACCESS_TEXT,
  localizeModelAccessIssue,
} from '../../locales/settingsModelAccess';
import { SETTINGS_LOCAL_MODELS_TEXT } from '../../locales/settingsLocalModels';
import type { GenerationBackendStatusResponse } from '../../types/systemConfig';
import type { LocalModelRuntimeState } from '../../types/localModels';
import {
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
  buildSettingsHref,
} from '../../routing/routes';
import {
  getProviderDisplayLabel,
  inspectConnectionSchemaDefinition,
} from './llmConnectionContract';
import { createLocalModelTransport } from './localModelTransport';
import {
  formatHubCheckedAt,
  localRuntimeStatusLabelKey,
  summarizeLocalCliStatus,
  summarizeLocalRuntimeStatus,
  type HubAvailability,
  type HubProbeState,
} from './modelSourcesHubStatus';
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
import { canEnableModelSource } from './modelSourceAvailability';
import {
  MODEL_SOURCE_STEPS,
  MODEL_SOURCE_TYPES,
  applyModelSourceSetupParams,
  clearModelSourceSetupParams,
  readModelSourceSetup,
  resolveModelSourceSetupRestore,
  type ModelSourceType,
} from './modelSourcesRoute';

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
  const accessText = MODEL_ACCESS_TEXT[language];
  const [searchParams, setSearchParams] = useSearchParams();
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
  const [connectionFilter, setConnectionFilter] = useState('');
  const [typePickerOpen, setTypePickerOpen] = useState(false);
  const localTransport = useMemo(() => createLocalModelTransport(), []);
  const [localRuntime, setLocalRuntime] = useState<LocalModelRuntimeState | null>(null);
  const [localRuntimeProbe, setLocalRuntimeProbe] = useState<HubProbeState>('loading');
  const [localRuntimeError, setLocalRuntimeError] = useState<string | null>(null);
  const [localRuntimeCheckedAt, setLocalRuntimeCheckedAt] = useState<number | null>(null);
  const [cliStatus, setCliStatus] = useState<GenerationBackendStatusResponse | null>(null);
  const [cliProbe, setCliProbe] = useState<HubProbeState>('loading');
  const [cliError, setCliError] = useState<string | null>(null);
  const [cliCheckedAt, setCliCheckedAt] = useState<number | null>(null);
  const localProbeRequestIdRef = useRef(0);
  const cliProbeRequestIdRef = useRef(0);
  /** Connection display labels auto-disabled after a failed connectivity test. */
  const [autoDisabledNotices, setAutoDisabledNotices] = useState<string[]>([]);
  const setupRestoredKeyRef = useRef<string | null>(null);

  const refreshLocalRuntime = useCallback(async (options?: { markLoading?: boolean }) => {
    const requestId = localProbeRequestIdRef.current + 1;
    localProbeRequestIdRef.current = requestId;
    if (options?.markLoading !== false) {
      setLocalRuntimeProbe('loading');
      setLocalRuntimeError(null);
    }
    try {
      const runtime = await localTransport.getRuntime();
      if (localProbeRequestIdRef.current !== requestId) {
        return;
      }
      setLocalRuntime(runtime);
      setLocalRuntimeProbe('idle');
      setLocalRuntimeCheckedAt(Date.now());
    } catch (error: unknown) {
      if (localProbeRequestIdRef.current !== requestId) {
        return;
      }
      const parsed = getParsedApiError(error, language);
      setLocalRuntime(null);
      setLocalRuntimeProbe('error');
      setLocalRuntimeError(parsed.message || parsed.rawMessage || null);
      setLocalRuntimeCheckedAt(Date.now());
    }
  }, [language, localTransport]);

  const refreshCliStatus = useCallback(async (options?: { markLoading?: boolean }) => {
    const requestId = cliProbeRequestIdRef.current + 1;
    cliProbeRequestIdRef.current = requestId;
    if (options?.markLoading !== false) {
      setCliProbe('loading');
      setCliError(null);
    }
    try {
      const status = await systemConfigApi.getGenerationBackendStatus();
      if (cliProbeRequestIdRef.current !== requestId) {
        return;
      }
      setCliStatus(status);
      setCliProbe('idle');
      setCliCheckedAt(Date.now());
    } catch (error: unknown) {
      if (cliProbeRequestIdRef.current !== requestId) {
        return;
      }
      const parsed = getParsedApiError(error, language);
      setCliStatus(null);
      setCliProbe('error');
      setCliError(parsed.message || parsed.rawMessage || null);
      setCliCheckedAt(Date.now());
    }
  }, [language]);

  const closeSetup = () => {
    // Suppress restore for the current setup key until query params are cleared.
    // Otherwise React can re-render with wizard closed while setup=1 is still in
    // the URL for one frame and re-open the full-page flow.
    const setup = readModelSourceSetup(searchParams);
    if (setup.active) {
      setupRestoredKeyRef.current = [
        setup.sourceType ?? '',
        setup.connection ?? '',
        setup.step ?? '',
      ].join('|');
    }
    setModal(null);
    setTypePickerOpen(false);
    // Explicit close clears shareable setup params so the hub is the durable URL.
    setSearchParams(clearModelSourceSetupParams(searchParams), { replace: true });
  };

  const navigateToLocalModels = () => {
    setSearchParams(new URLSearchParams(
      buildSettingsHref({
        section: SETTINGS_SECTION_IDS.aiModels,
        view: SETTINGS_VIEW_IDS.aiModels.localModels,
      }).split('?')[1] ?? '',
    ), { replace: false });
  };

  const navigateToCliBackend = () => {
    if (onViewDiagnostics) {
      onViewDiagnostics();
      return;
    }
    setSearchParams(new URLSearchParams(
      buildSettingsHref({
        section: 'advanced',
        view: 'raw_config',
      }).split('?')[1] ?? '',
    ), { replace: false });
  };

  const navigateToTaskRouting = () => {
    if (onManageModels) {
      onManageModels();
      return;
    }
    setSearchParams(new URLSearchParams(
      buildSettingsHref({
        section: SETTINGS_SECTION_IDS.aiModels,
        view: SETTINGS_VIEW_IDS.aiModels.taskRouting,
      }).split('?')[1] ?? '',
    ), { replace: false });
  };

  const chooseSourceType = (sourceType: ModelSourceType) => {
    setTypePickerOpen(false);
    if (sourceType === MODEL_SOURCE_TYPES.cloud) {
      setModal({ mode: 'add' });
      return;
    }
    setModal(null);
    if (sourceType === MODEL_SOURCE_TYPES.localServer) {
      navigateToLocalModels();
      return;
    }
    navigateToCliBackend();
  };

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
    setTypePickerOpen(false);
    setPendingRemove(null);
  }

  // The page-level "Add model source" button opens the type picker first.
  const [prevAddSignal, setPrevAddSignal] = useState(addSignal);
  if (prevAddSignal !== addSignal) {
    setPrevAddSignal(addSignal);
    if (!mutationBusy) {
      setTypePickerOpen(true);
      setModal(null);
    }
  }

  // Clear restore tracking when the parent requests a new Add-source session.
  // Must not write refs during render (react-hooks/refs).
  useEffect(() => {
    if (addSignal === 0) {
      return;
    }
    setupRestoredKeyRef.current = null;
  }, [addSignal]);

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
    // Initial probe: state already starts as loading; avoid sync setState-in-effect.
    // User-triggered recheck uses markLoading (default true) outside effects.
    let cancelled = false;
    const requestLocal = localProbeRequestIdRef.current + 1;
    localProbeRequestIdRef.current = requestLocal;
    const requestCli = cliProbeRequestIdRef.current + 1;
    cliProbeRequestIdRef.current = requestCli;

    void localTransport.getRuntime()
      .then((runtime) => {
        if (cancelled || localProbeRequestIdRef.current !== requestLocal) {
          return;
        }
        setLocalRuntime(runtime);
        setLocalRuntimeProbe('idle');
        setLocalRuntimeCheckedAt(Date.now());
      })
      .catch((error: unknown) => {
        if (cancelled || localProbeRequestIdRef.current !== requestLocal) {
          return;
        }
        const parsed = getParsedApiError(error, language);
        setLocalRuntime(null);
        setLocalRuntimeProbe('error');
        setLocalRuntimeError(parsed.message || parsed.rawMessage || null);
        setLocalRuntimeCheckedAt(Date.now());
      });

    void systemConfigApi.getGenerationBackendStatus()
      .then((status) => {
        if (cancelled || cliProbeRequestIdRef.current !== requestCli) {
          return;
        }
        setCliStatus(status);
        setCliProbe('idle');
        setCliCheckedAt(Date.now());
      })
      .catch((error: unknown) => {
        if (cancelled || cliProbeRequestIdRef.current !== requestCli) {
          return;
        }
        const parsed = getParsedApiError(error, language);
        setCliStatus(null);
        setCliProbe('error');
        setCliError(parsed.message || parsed.rawMessage || null);
        setCliCheckedAt(Date.now());
      });

    return () => {
      cancelled = true;
      localProbeRequestIdRef.current += 1;
      cliProbeRequestIdRef.current += 1;
    };
  }, [language, localTransport]);

  // Restore route-backed setup from shareable query params (refresh / deep link).
  useEffect(() => {
    const setup = readModelSourceSetup(searchParams);
    if (!setup.active) {
      setupRestoredKeyRef.current = null;
      return;
    }
    const restoreKey = [
      setup.sourceType ?? '',
      setup.connection ?? '',
      setup.step ?? '',
    ].join('|');
    // Already handling this setup key (opened by UI or previously restored).
    if (setupRestoredKeyRef.current === restoreKey) {
      return;
    }
    if (typePickerOpen || modal) {
      setupRestoredKeyRef.current = restoreKey;
      return;
    }
    if (mutationBusy) {
      return;
    }
    const knownNames = channels.map((channel) => channel.name);
    const action = resolveModelSourceSetupRestore(searchParams, knownNames);
    setupRestoredKeyRef.current = restoreKey;
    // Defer React state updates out of the effect body (react-hooks/set-state-in-effect).
    queueMicrotask(() => {
      if (action.kind === 'type_picker') {
        setTypePickerOpen(true);
        return;
      }
      if (action.kind === 'cloud_add') {
        setTypePickerOpen(false);
        setModal({ mode: 'add' });
        return;
      }
      if (action.kind === 'cloud_edit') {
        const index = channels.findIndex((channel) => channel.name === action.connection);
        if (index >= 0) {
          setTypePickerOpen(false);
          setModal({ mode: 'edit', index, focusModels: action.focusModels });
        } else {
          setTypePickerOpen(true);
        }
        return;
      }
      if (action.kind === 'navigate_local_server') {
        navigateToLocalModels();
        return;
      }
      if (action.kind === 'navigate_local_cli') {
        navigateToCliBackend();
      }
    });
    // navigate actions leave the hub; setup params are replaced by the target view URL.
  }, [channels, modal, mutationBusy, searchParams, typePickerOpen]);

  // Keep setup query params aligned while the wizard session is open.
  useEffect(() => {
    if (!typePickerOpen && !modal) {
      return;
    }
    let next: URLSearchParams | null = null;
    if (typePickerOpen) {
      next = applyModelSourceSetupParams(searchParams, {
        step: MODEL_SOURCE_STEPS.type,
        sourceType: null,
        connection: null,
      });
    } else if (modal?.mode === 'add') {
      next = applyModelSourceSetupParams(searchParams, {
        sourceType: MODEL_SOURCE_TYPES.cloud,
        step: MODEL_SOURCE_STEPS.provider,
        connection: null,
      });
    } else if (modal?.mode === 'edit') {
      const channel = channels[modal.index];
      next = applyModelSourceSetupParams(searchParams, {
        sourceType: MODEL_SOURCE_TYPES.cloud,
        step: modal.focusModels ? MODEL_SOURCE_STEPS.models : MODEL_SOURCE_STEPS.connect,
        connection: channel?.name ?? null,
      });
    }
    if (!next) return;
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [typePickerOpen, modal, channels, searchParams, setSearchParams]);

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
    const markUnavailableAfterFailedTest = (target: ChannelConfig, errorText: string) => {
      setTestStates((previous) => ({
        ...previous,
        [target.id]: { status: 'error', text: errorText },
      }));
      if (!target.enabled) {
        return;
      }
      // Failed sources must not remain available for task routing.
      setChannels((previous) => previous.map((item) => (
        item.id === target.id
          ? { ...item, enabled: false, enabledValuePresent: true }
          : item
      )));
      const label = target.displayName.trim() || target.name;
      setAutoDisabledNotices((previous) => (
        previous.includes(label) ? previous : [...previous, label]
      ));
    };

    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hermesSecretPersisted)) {
      markUnavailableAfterFailedTest(channel, MODEL_ACCESS_TEXT[language].runtimeSecret);
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
    if (result.status === 'error') {
      markUnavailableAfterFailedTest(channel, result.text || accessText.testFailed);
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
        setTypePickerOpen(false);
        setModal({ mode: 'edit', index });
        return;
      }
      if (!canEnableModelSource({
        testState: testStates[channel.id],
        requireSuccessfulTest: true,
      })) {
        setTypePickerOpen(false);
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
    closeSetup();
  };

  const normalizedFilter = connectionFilter.trim().toLowerCase();
  const visibleChannels = useMemo(() => {
    return channels
      .map((channel, index) => ({ channel, index }))
      .filter(({ channel }) => {
        if (!normalizedFilter) {
          return true;
        }
        const provider = findCatalogProvider(providers, channel.providerId);
        const providerLabel = provider
          ? getProviderDisplayLabel(provider, language)
          : channel.providerId;
        return [
          channel.name,
          channel.displayName,
          channel.providerId,
          providerLabel,
          channel.models,
          channel.baseUrl,
          editorText.hubCloudGroup,
        ].join(' ').toLowerCase().includes(normalizedFilter);
      });
  }, [channels, connectionFilter, editorText.hubCloudGroup, language, normalizedFilter, providers]);

  const primaryModel = initialRuntimeConfig.primaryModel.trim();
  const agentModel = initialRuntimeConfig.agentPrimaryModel.trim();
  const visionModel = initialRuntimeConfig.visionModel.trim();
  const localModelsText = SETTINGS_LOCAL_MODELS_TEXT[language];
  const localSummary = useMemo(
    () => summarizeLocalRuntimeStatus(localRuntimeProbe, localRuntime, localRuntimeError),
    [localRuntime, localRuntimeError, localRuntimeProbe],
  );
  const cliSummary = useMemo(
    () => summarizeLocalCliStatus(cliProbe, cliStatus, cliError),
    [cliError, cliProbe, cliStatus],
  );
  const localeTag = UI_LANGUAGE_METADATA[language]?.intlLocale ?? 'en';
  const localCheckedLabel = formatHubCheckedAt(localRuntimeCheckedAt, localeTag);
  const cliCheckedLabel = formatHubCheckedAt(cliCheckedAt, localeTag);
  const localConfig = localRuntime?.configuration;
  const registeredCount = localConfig?.registeredModels?.length ?? 0;
  const localPrimary = (localConfig?.primaryModel || '').trim();
  const localAgent = (localConfig?.agentModel || '').trim();
  const localStatusLabel = (() => {
    const key = localRuntimeStatusLabelKey(localRuntime?.status);
    return (localModelsText as Record<string, string>)[key] ?? localRuntime?.status ?? '';
  })();
  const availabilityLabel = (availability: HubAvailability): string => {
    switch (availability) {
      case 'available':
        return editorText.hubStatusAvailable;
      case 'unavailable':
        return editorText.hubStatusUnavailable;
      case 'not_configured':
        return editorText.hubStatusNotConfigured;
      case 'failed':
        return editorText.hubStatusFailed;
      case 'starting':
        return editorText.hubStatusStarting;
      case 'loading':
      default:
        return editorText.hubStatusLoading;
    }
  };
  const localRuntimeLabel = localRuntime?.status || 'unknown';
  const localMatches = !normalizedFilter
    || editorText.hubLocalGroup.toLowerCase().includes(normalizedFilter)
    || 'ollama'.includes(normalizedFilter)
    || localPrimary.toLowerCase().includes(normalizedFilter)
    || localRuntimeLabel.toLowerCase().includes(normalizedFilter)
    || availabilityLabel(localSummary.availability).toLowerCase().includes(normalizedFilter);
  const cliPrimary = cliStatus?.primary;
  const cliIsLocal = cliPrimary?.backendType === 'local_cli';
  const cliMatches = !normalizedFilter
    || editorText.hubCliGroup.toLowerCase().includes(normalizedFilter)
    || 'cli'.includes(normalizedFilter)
    || (cliPrimary?.backendId || '').toLowerCase().includes(normalizedFilter)
    || (cliPrimary?.backendType || '').toLowerCase().includes(normalizedFilter)
    || availabilityLabel(cliSummary.availability).toLowerCase().includes(normalizedFilter);
  const hasAnyMatch = visibleChannels.length > 0 || localMatches || cliMatches || channels.length === 0;
  const setupOpen = Boolean(modal) || typePickerOpen;

  return (
    <div className="space-y-4" data-testid={setupOpen ? 'model-sources-hub-wizard' : 'model-sources-hub'}>
      {setupOpen ? (
        <div className="space-y-4">
          {typePickerOpen ? (
            <section
              className="space-y-4 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4 sm:p-5"
              data-testid="model-source-type-picker"
              aria-labelledby="model-source-type-heading"
            >
              <div className="space-y-1">
                <h2 id="model-source-type-heading" className="text-base font-semibold text-foreground">
                  {editorText.hubTypePickerTitle}
                </h2>
                <p className="text-sm text-secondary-text">{editorText.hubTypePickerDescription}</p>
                <p className="text-xs text-muted-text">{accessText.setupLifecycleHint}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {([
                  {
                    type: MODEL_SOURCE_TYPES.cloud,
                    title: editorText.hubTypeCloud,
                    description: editorText.hubTypeCloudDescription,
                    testId: 'source-type-cloud',
                  },
                  {
                    type: MODEL_SOURCE_TYPES.localServer,
                    title: editorText.hubTypeLocal,
                    description: editorText.hubTypeLocalDescription,
                    testId: 'source-type-local',
                  },
                  {
                    type: MODEL_SOURCE_TYPES.localCli,
                    title: editorText.hubTypeCli,
                    description: editorText.hubTypeCliDescription,
                    testId: 'source-type-cli',
                  },
                ] as const).map((option) => (
                  <button
                    key={option.type}
                    type="button"
                    data-testid={option.testId}
                    disabled={busy}
                    onClick={() => chooseSourceType(option.type)}
                    className="rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] px-4 py-4 text-left transition hover:border-[var(--settings-border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <p className="text-sm font-semibold text-foreground">{option.title}</p>
                    <p className="mt-1 text-xs leading-5 text-secondary-text">{option.description}</p>
                  </button>
                ))}
              </div>
              <div className="flex justify-end">
                <button
                  type="button"
                  className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                  onClick={closeSetup}
                >
                  {accessText.closeSetup}
                </button>
              </div>
            </section>
          ) : null}

          {modal ? (
            <ConnectionModal
              presentation="page"
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
              onManageModels={navigateToTaskRouting}
              canReplaceModelReferences={Boolean(onReplaceModelReferences)}
              onSubmit={handleModalSubmit}
              onClose={closeSetup}
            />
          ) : null}
        </div>
      ) : null}

      <div
        className={setupOpen ? 'hidden' : 'space-y-4'}
        aria-hidden={setupOpen ? true : undefined}
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

      <section
        className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
        data-testid="model-sources-active-header"
        aria-labelledby="model-sources-active-heading"
      >
        <h3 id="model-sources-active-heading" className="text-sm font-semibold text-foreground">
          {editorText.hubActiveHeader}
        </h3>
        <p className="text-xs text-secondary-text">
          {primaryModel
            ? formatUiText(editorText.hubPrimaryModel, { model: primaryModel })
            : editorText.hubNoPrimary}
        </p>
        {agentModel ? (
          <p className="text-xs text-secondary-text">
            {formatUiText(editorText.hubAgentModel, { model: agentModel })}
          </p>
        ) : null}
        {visionModel ? (
          <p className="text-xs text-secondary-text">
            {formatUiText(editorText.hubVisionModel, { model: visionModel })}
          </p>
        ) : null}
        <p className="text-xs text-muted-text">{accessText.setupLifecycleHint}</p>
      </section>

      {autoDisabledNotices.length > 0 ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={editorText.hubAutoDisabledTitle}
          message={(
            <div className="space-y-1" data-testid="model-sources-auto-disabled-notice">
              <p>{formatUiText(editorText.hubAutoDisabledMessage, {
                sources: autoDisabledNotices.join(getUiListSeparator(language)),
              })}</p>
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                onClick={() => setAutoDisabledNotices([])}
              >
                {editorText.hubAutoDisabledDismiss}
              </button>
            </div>
          )}
        />
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

      <SearchInput
        value={connectionFilter}
        onChange={(event) => setConnectionFilter(event.target.value)}
        placeholder={editorText.hubSearchPlaceholder}
        aria-label={editorText.hubSearchLabel}
        wrapperClassName="w-full sm:max-w-sm"
        data-testid="model-sources-filter"
      />

      {!hasAnyMatch ? (
        <p className="px-1 text-sm text-muted-text" role="status" data-testid="model-sources-no-matches">
          {editorText.hubNoSearchMatches}
        </p>
      ) : null}

      <section className="space-y-2" aria-labelledby="cloud-connections-heading" data-testid="model-sources-cloud-group">
        <h3 id="cloud-connections-heading" className="text-sm font-semibold text-foreground">
          {editorText.hubCloudGroup}
        </h3>
        {channels.length === 0 ? (
          <div className="settings-surface-overlay-muted rounded-xl border border-dashed settings-border-strong px-4 py-10 text-center">
            <p className="text-sm font-medium text-secondary-text">{editorText.emptyTitle}</p>
            <p className="mt-1 text-xs text-muted-text">{editorText.emptyDescription}</p>
          </div>
        ) : visibleChannels.length === 0 ? (
          normalizedFilter ? null : (
            <p className="text-xs text-muted-text">{editorText.hubNoSearchMatches}</p>
          )
        ) : (
          <div className="space-y-2">
            {visibleChannels.map(({ channel, index }) => (
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
            ))}
          </div>
        )}
      </section>

      {localMatches ? (
        <section
          className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
          data-testid="model-sources-local-group"
          aria-labelledby="model-sources-local-heading"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusDot
                tone={localSummary.tone}
                pulse={localSummary.pulse}
                aria-label={availabilityLabel(localSummary.availability)}
              />
              <h3 id="model-sources-local-heading" className="text-sm font-semibold text-foreground">
                {editorText.hubLocalGroup}
              </h3>
              <span
                className="text-xs text-secondary-text"
                data-testid="model-sources-local-availability"
              >
                {availabilityLabel(localSummary.availability)}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                onClick={() => void refreshLocalRuntime()}
                disabled={localRuntimeProbe === 'loading'}
              >
                {editorText.hubLocalRecheck}
              </button>
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                onClick={navigateToLocalModels}
              >
                {editorText.hubLocalManage}
              </button>
            </div>
          </div>
          {localSummary.availability === 'loading' ? (
            <p className="text-xs text-muted-text" data-testid="model-sources-local-loading">
              {editorText.hubLocalLoading}
            </p>
          ) : localSummary.availability === 'failed' ? (
            <div className="space-y-1 text-xs text-danger" data-testid="model-sources-local-error">
              <p>{editorText.hubLocalFailed}</p>
              {localSummary.failureReason ? (
                <p>
                  {formatUiText(editorText.hubLocalFailedReason, {
                    reason: localSummary.failureReason,
                  })}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-1 text-xs text-secondary-text" data-testid="model-sources-local-details">
              {localStatusLabel ? (
                <p>{formatUiText(editorText.hubLocalStatus, { status: localStatusLabel })}</p>
              ) : null}
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
          {localCheckedLabel ? (
            <p className="text-xs text-muted-text" data-testid="model-sources-local-checked-at">
              {formatUiText(editorText.hubLocalCheckedAt, { time: localCheckedLabel })}
            </p>
          ) : null}
        </section>
      ) : null}

      {cliMatches ? (
        <section
          className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
          data-testid="model-sources-cli-group"
          aria-labelledby="model-sources-cli-heading"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusDot
                tone={cliSummary.tone}
                pulse={cliSummary.pulse}
                aria-label={availabilityLabel(cliSummary.availability)}
              />
              <h3 id="model-sources-cli-heading" className="text-sm font-semibold text-foreground">
                {editorText.hubCliGroup}
              </h3>
              <span
                className="text-xs text-secondary-text"
                data-testid="model-sources-cli-availability"
              >
                {availabilityLabel(cliSummary.availability)}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                onClick={() => void refreshCliStatus()}
                disabled={cliProbe === 'loading'}
              >
                {editorText.hubCliRecheck}
              </button>
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
                onClick={navigateToCliBackend}
              >
                {editorText.hubCliManage}
              </button>
            </div>
          </div>
          {cliSummary.availability === 'loading' ? (
            <p className="text-xs text-muted-text" data-testid="model-sources-cli-loading">
              {editorText.hubCliLoading}
            </p>
          ) : cliSummary.availability === 'failed' ? (
            <div className="space-y-1 text-xs text-danger" data-testid="model-sources-cli-error">
              <p>{editorText.hubCliFailed}</p>
              {cliSummary.failureReason ? (
                <p>
                  {formatUiText(editorText.hubCliFailedReason, {
                    reason: cliSummary.failureReason,
                  })}
                </p>
              ) : null}
            </div>
          ) : cliIsLocal && cliPrimary ? (
            <div className="space-y-1 text-xs text-secondary-text" data-testid="model-sources-cli-details">
              <p>{formatUiText(editorText.hubCliActive, { backend: cliPrimary.backendId })}</p>
              {cliStatus?.fallback?.backendId ? (
                <p>{formatUiText(editorText.hubCliFallback, { backend: cliStatus.fallback.backendId })}</p>
              ) : null}
              {cliSummary.failureReason ? (
                <p className="text-warning">
                  {formatUiText(editorText.hubCliFailedReason, {
                    reason: cliSummary.failureReason,
                  })}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-secondary-text" data-testid="model-sources-cli-none">
              {editorText.hubCliNone}
            </p>
          )}
          {cliCheckedLabel ? (
            <p className="text-xs text-muted-text" data-testid="model-sources-cli-checked-at">
              {formatUiText(editorText.hubCliCheckedAt, { time: cliCheckedLabel })}
            </p>
          ) : null}
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

      {channels.some((channel) => channel.enabled) ? (
        <div className="flex items-center justify-end px-1">
          <button
            type="button"
            className="settings-accent-text inline-flex min-h-11 min-w-11 items-center text-xs underline-offset-2 hover:underline"
            onClick={navigateToTaskRouting}
          >
            {editorText.assignModels}
          </button>
        </div>
      ) : null}
      </div>

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
              navigateToTaskRouting();
            } else {
              removeChannel(pendingRemove.index);
            }
          }
          setPendingRemove(null);
        }}
        onCancel={() => setPendingRemove(null)}
      />
    </div>
  );
};
