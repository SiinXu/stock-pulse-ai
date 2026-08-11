import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  alphasiftApi,
  type AlphaSiftCandidate,
  type AlphaSiftHotspotDetail,
  type AlphaSiftHotspot,
  type AlphaSiftScreenResponse,
  type AlphaSiftScreenTaskStatus,
  type AlphaSiftStrategy,
} from '../api/alphasift';
import {
  formatParsedApiError,
  getParsedApiError,
  toApiErrorMessage,
} from '../api/error';
import { AppPage } from '../components/common';
import { ScreeningConfigurationModal } from '../components/screening/ScreeningConfigurationModal';
import { ScreeningHotspotsSection } from '../components/screening/ScreeningHotspotsSection';
import ScreeningPageAlerts from '../components/screening/ScreeningPageAlerts';
import ScreeningPageHeader from '../components/screening/ScreeningPageHeader';
import { ScreeningResultsSection } from '../components/screening/ScreeningResultsSection';
import { ScreeningRunStatusCard } from '../components/screening/ScreeningRunStatusCard';
import { ScreeningStrategyBar } from '../components/screening/ScreeningStrategyBar';
import { formatHotspotEmptyMessage } from '../components/screening/hotspotModel';
import { getScreeningDegradationReasons } from '../components/screening/screeningDegradation';
import createScreeningResultsEmptyState from '../components/screening/screeningResultsEmptyState';
import {
  getScreeningCapabilityLabel,
  getScreeningResultsEmptyKind,
  getScreeningRunStatusTitle,
  isFullSourceUnavailable,
  isScreeningAttemptLoading,
  type ScreeningAttemptState,
  type ScreeningSuccessfulRun,
} from '../components/screening/screeningPageState';
import { useScreeningCapability } from '../components/screening/useScreeningCapability';
import {
  SCREEN_TASK_POLL_INTERVAL_MS,
  clearPersistedScreenTask,
  formatRecoverableScreenTaskPollingError,
  isRunningScreenTask,
  isUnrecoverableScreenTaskError,
  persistScreenTask,
  readPersistedScreenTask,
  readScreeningRunParameters,
  type PersistedScreenTask,
  type ScreeningRunParameters,
} from '../components/screening/screeningRunState';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText } from '../i18n/uiText';
import {
  RESEARCH_DISCOVER_LIMITS,
  RESEARCH_DISCOVER_MARKET_VALUES,
  buildSettingsHref,
} from '../routing/routes';
import {
  DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
} from '../routing/researchRouteState';
import { SCREENING_TEXT } from '../locales/screening';
import { buildDeepLink } from '../utils/deepLink';
import { formatTaskMessage } from '../utils/taskMessage';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { useScreeningUrlState } from '../components/screening/useScreeningUrlState';

const StockScreeningPage: React.FC = () => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const configurationFormId = useId();
  const text = SCREENING_TEXT[language];
  const markets = useMemo(
    () => [{ id: RESEARCH_DISCOVER_MARKET_VALUES.china, label: text.marketCn }],
    [text.marketCn],
  );
  const [restoredTask] = useState<PersistedScreenTask | null>(() => readPersistedScreenTask());
  const [initialRunParameters] = useState<ScreeningRunParameters>(() => readScreeningRunParameters(restoredTask));
  const [market, setMarket] = useState(initialRunParameters.market);
  const [strategy, setStrategy] = useState(initialRunParameters.strategy);
  const [strategies, setStrategies] = useState<AlphaSiftStrategy[]>([]);
  const [maxResults, setMaxResults] = useState(initialRunParameters.maxResults);
  const [maxResultsDraft, setMaxResultsDraft] = useState(String(initialRunParameters.maxResults));
  const [maxResultsError, setMaxResultsError] = useState('');
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [configurationError, setConfigurationError] = useState('');
  const [hotspots, setHotspots] = useState<AlphaSiftHotspot[]>([]);
  const [hotspotsUpdatedAt, setHotspotsUpdatedAt] = useState<string | null>(null);
  const strategiesRequestIdRef = useRef(0);
  const hotspotsRequestIdRef = useRef(0);
  const hotspotDetailRequestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const hotspotDetailsByTopicRef = useRef<Record<string, AlphaSiftHotspotDetail>>({});
  const [hotspotDetail, setHotspotDetail] = useState<AlphaSiftHotspotDetail | null>(null);
  const [loadingHotspotDetail, setLoadingHotspotDetail] = useState(false);
  const [hotspotDetailError, setHotspotDetailError] = useState('');
  const [loadingHotspots, setLoadingHotspots] = useState(false);
  const [hotspotError, setHotspotError] = useState('');
  const [lastSuccessfulRun, setLastSuccessfulRun] = useState<ScreeningSuccessfulRun | null>(null);
  const [attemptResult, setAttemptResult] = useState<AlphaSiftScreenResponse | null>(null);
  const [attemptState, setAttemptState] = useState<ScreeningAttemptState>(
    restoredTask?.taskId ? 'running' : 'idle',
  );
  const lastValidatedParametersRef = useRef<ScreeningRunParameters | null>(
    restoredTask
      ? {
          market: restoredTask.market,
          strategy: restoredTask.strategy,
          maxResults: restoredTask.maxResults,
        }
      : null,
  );
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [error, setError] = useState('');
  const [strategyLoadError, setStrategyLoadError] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(restoredTask?.taskId ?? null);
  const [taskProgress, setTaskProgress] = useState(restoredTask?.taskId ? 10 : 0);
  const [taskMessage, setTaskMessage] = useState(restoredTask?.taskId ? text.restoringTask : '');

  const {
    expandedCode,
    setExpandedCode,
    hotspotsExpanded,
    selectedHotspotTopic,
    setSelectedHotspotTopic,
    selectedHotspotTopicRef,
    handleExpandedCodeChange,
    handleHotspotSelect: selectHotspotInUrl,
    toggleHotspotsExpanded: toggleHotspotsInUrl,
    clearCandidateFromUrl,
  } = useScreeningUrlState(
    { market, strategy, maxResults },
    { setMarket, setStrategy, setMaxResults, setMaxResultsDraft },
  );

  const selectedStrategy = useMemo(() => strategies.find((item) => item.id === strategy), [strategies, strategy]);
  const selectedStrategyDisplay = useMemo(
    () => selectedStrategy ? getStrategyDisplay(selectedStrategy, language) : null,
    [language, selectedStrategy],
  );
  const selectedStrategyTag = selectedStrategyDisplay?.category || text.custom;
  const displayedStrategy = selectedStrategyDisplay?.name ?? `${text.customStrategy} (${strategy})`;
  const strategyOptions = useMemo(() => {
    const catalogOptions = strategies.map((item) => ({
      value: item.id,
      label: getStrategyDisplay(item, language).name,
    }));
    if (selectedStrategy || strategy === DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.strategy) {
      return catalogOptions;
    }
    return [{ value: strategy, label: displayedStrategy }, ...catalogOptions];
  }, [displayedStrategy, language, selectedStrategy, strategies, strategy]);
  const handleOpenDataSources = useCallback(() => {
    navigate(buildSettingsHref({ section: 'data_sources', view: 'providers' }));
  }, [navigate]);
  const handleAdminLogin = useCallback(() => {
    const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    navigate(`/login?redirect=${encodeURIComponent(redirect)}`);
  }, [navigate]);
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const applyScreenResult = useCallback((result: AlphaSiftScreenResponse) => {
    const nextCandidates = result.candidates || [];
    const parameters = lastValidatedParametersRef.current;
    setAttemptResult(result);
    setAttemptState('completed');
    setError('');
    if (!isFullSourceUnavailable(result) && parameters) {
      setLastSuccessfulRun({ result, parameters });
      setExpandedCode((current) => {
        if (current && nextCandidates.some((item) => item.code === current)) return current;
        return nextCandidates[0]?.code ?? null;
      });
    } else if (!lastSuccessfulRun) {
      setExpandedCode(null);
    }
  }, [lastSuccessfulRun, setExpandedCode]);
  const clearScreeningResults = () => {
    setLastSuccessfulRun(null);
    setAttemptResult(null);
    setAttemptState('idle');
    setExpandedCode(null);
    clearCandidateFromUrl();
    setError('');
  };
  const loadHotspotDetail = useCallback(async (topic: string, options: { refresh?: boolean } = {}) => {
    if (!topic) return;
    const cachedDetail = !options.refresh ? hotspotDetailsByTopicRef.current[topic] : null;
    if (cachedDetail) {
      setHotspotDetail(cachedDetail);
      setHotspotDetailError('');
      setLoadingHotspotDetail(false);
      return;
    }
    const requestId = hotspotDetailRequestIdRef.current + 1;
    hotspotDetailRequestIdRef.current = requestId;
    const isCurrentRequest = () => hotspotDetailRequestIdRef.current === requestId;
    const canApplyRequest = () => isCurrentRequest() && selectedHotspotTopicRef.current === topic;
    setLoadingHotspotDetail(true);
    setHotspotDetail((currentDetail) => (currentDetail?.topic === topic ? currentDetail : null));
    setHotspotDetailError('');
    try {
      const detail = await alphasiftApi.getHotspotDetail({ topic, provider: 'akshare', refresh: options.refresh ?? false });
      if (!canApplyRequest()) return;
      hotspotDetailsByTopicRef.current = { ...hotspotDetailsByTopicRef.current, [topic]: detail };
      setHotspotDetail(detail);
    } catch (err) {
      if (!canApplyRequest()) return;
      setHotspotDetail(null);
      setHotspotDetailError(toApiErrorMessage(err, text.hotspotDetailLoadFailed, language));
    } finally {
      if (isCurrentRequest()) setLoadingHotspotDetail(false);
    }
  }, [language, selectedHotspotTopicRef, text.hotspotDetailLoadFailed]);

  const loadStrategies = useCallback(async () => {
    const requestId = strategiesRequestIdRef.current + 1;
    strategiesRequestIdRef.current = requestId;
    const isLatestRequest = () => strategiesRequestIdRef.current === requestId;
    setLoadingStrategies(true);
    setStrategyLoadError('');
    try {
      const result = await alphasiftApi.getStrategies();
      if (!isLatestRequest()) return;
      setStrategies(result.strategies || []);
    } catch (err) {
      if (!isLatestRequest()) return;
      setStrategyLoadError(getParsedApiError(err, language).message || text.strategyLoadFailed);
    } finally {
      if (isLatestRequest()) setLoadingStrategies(false);
    }
  }, [language, text.strategyLoadFailed]);

  const loadHotspots = useCallback(async (refresh = false) => {
    const requestId = hotspotsRequestIdRef.current + 1;
    hotspotsRequestIdRef.current = requestId;
    const isLatestRequest = () => hotspotsRequestIdRef.current === requestId;
    setLoadingHotspots(true);
    setHotspotError('');
    try {
      const result = await alphasiftApi.getHotspots({ provider: 'akshare', top: 12, refresh });
      if (!isLatestRequest()) return;
      const nextHotspots = result.hotspots || [];
      const nextDetails = result.details || {};
      hotspotDetailsByTopicRef.current = { ...hotspotDetailsByTopicRef.current, ...nextDetails };
      const currentTopic = selectedHotspotTopicRef.current;
      const retainedTopic = Boolean(currentTopic && nextHotspots.some((item) => item.topic === currentTopic));
      const nextTopic = retainedTopic ? currentTopic : null;
      setHotspots(nextHotspots);
      setHotspotsUpdatedAt(result.cachedAt || (nextHotspots.length > 0 ? new Date().toISOString() : null));
      if (!retainedTopic) {
        selectedHotspotTopicRef.current = null;
        setSelectedHotspotTopic(null);
      } else {
        setSelectedHotspotTopic(nextTopic);
      }
      if (nextTopic && nextDetails[nextTopic]) {
        setHotspotDetail(nextDetails[nextTopic]);
        setLoadingHotspotDetail(false);
      } else if (retainedTopic && refresh && nextTopic) {
        void loadHotspotDetail(nextTopic, { refresh: true });
      } else if (!retainedTopic) {
        setHotspotDetail(null);
      }
      setHotspotDetailError('');
      if (nextHotspots.length === 0) {
        setHotspotError(formatHotspotEmptyMessage(result, text));
      }
    } catch (err) {
      if (!isLatestRequest()) return;
      setHotspotError(toApiErrorMessage(err, text.hotspotLoadFailed, language));
    } finally {
      if (isLatestRequest()) setLoadingHotspots(false);
    }
  }, [language, loadHotspotDetail, selectedHotspotTopicRef, setSelectedHotspotTopic, text]);

  const handleHotspotSelect = useCallback((topic: string) => {
    const cachedDetail = hotspotDetailsByTopicRef.current[topic];
    selectHotspotInUrl(topic);
    if (cachedDetail) {
      setHotspotDetail(cachedDetail);
      setHotspotDetailError('');
      setLoadingHotspotDetail(false);
    } else {
      setHotspotDetail((currentDetail) => (currentDetail?.topic === topic ? currentDetail : null));
    }
  }, [selectHotspotInUrl]);

  const toggleHotspotsExpanded = useCallback(() => {
    toggleHotspotsInUrl();
    if (hotspotsExpanded) {
      setHotspotDetail(null);
      setHotspotDetailError('');
    }
  }, [hotspotsExpanded, toggleHotspotsInUrl]);

  const handleAnalyzeHotspotStock = useCallback((stock: AlphaSiftHotspotDetail['stocks'][number]) => {
    const stockCode = String(stock.code || '').trim();
    if (!stockCode) return;
    // #879 A4: shareable Home stock intent via query (not location.state).
    try {
      navigate(buildDeepLink({ page: 'home', stockCode }));
    } catch {
      navigate(`/?stock=${encodeURIComponent(stockCode)}`);
    }
  }, [navigate]);

  useEffect(() => {
    selectedHotspotTopicRef.current = selectedHotspotTopic;
  }, [selectedHotspotTopic, selectedHotspotTopicRef]);

  useEffect(() => {
    if (!selectedHotspotTopic) return;
    void loadHotspotDetail(selectedHotspotTopic);
  }, [loadHotspotDetail, selectedHotspotTopic]);

  const {
    capability,
    enabling,
    actionError: capabilityActionError,
    loadStatus,
    enable: enableScreening,
  } = useScreeningCapability({
    language,
    enableFailedText: text.enableFailed,
    loadStrategies,
    loadHotspots,
  });
  const loading = isScreeningAttemptLoading(attemptState);
  const showingLastGood = Boolean(
    lastSuccessfulRun
    && (
      loading
      || attemptState === 'failed'
      || capability.state === 'status_error'
      || isFullSourceUnavailable(attemptResult)
    ),
  );
  const displayedResult = showingLastGood
    ? lastSuccessfulRun?.result ?? null
    : attemptResult ?? lastSuccessfulRun?.result ?? null;
  const screenMeta = displayedResult;
  const candidates: AlphaSiftCandidate[] = displayedResult?.candidates ?? [];
  const degradationReasons = useMemo(
    () => getScreeningDegradationReasons(attemptResult ?? screenMeta, text),
    [attemptResult, screenMeta, text],
  );
  const llmDegraded = screenMeta?.llmRanked === false;
  const isScreeningEnabled = capability.state === 'ready';
  const resultsEmptyKind = useMemo(
    () => getScreeningResultsEmptyKind({
      capability: capability.state,
      loading,
      candidatesCount: candidates.length,
      screenMeta: attemptResult ?? screenMeta,
    }),
    [attemptResult, candidates.length, capability.state, loading, screenMeta],
  );
  const statusText = getScreeningCapabilityLabel(capability.state, text);
  const runStatusTitle = getScreeningRunStatusTitle({
    text, attemptState, candidatesCount: candidates.length, screenMeta, attemptResult,
  });

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      strategiesRequestIdRef.current += 1;
      hotspotsRequestIdRef.current += 1;
      hotspotDetailRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!activeTaskId) return undefined;
    const pollingTaskId = activeTaskId;
    let active = true;
    let timer: number | undefined;

    function finishTask() {
      clearPersistedScreenTask();
      setActiveTaskId(null);
    }

    function applyTaskStatus(task: AlphaSiftScreenTaskStatus) {
      const nextProgress = Number(task.progress ?? 0);
      setTaskProgress(Number.isFinite(nextProgress) ? nextProgress : 0);
      setTaskMessage(formatTaskMessage(task, language));

      if (task.status === 'completed') {
        if (task.result) {
          applyScreenResult(task.result);
        } else {
          setError(text.noTaskResults);
          setAttemptResult(null);
          setAttemptState('failed');
        }
        finishTask();
        return;
      }

      if (task.status === 'failed') {
        setAttemptResult(null);
        setAttemptState('failed');
        setError(getParsedApiError({
          error: 'alphasift_screen_failed',
          message: task.error || task.message || 'Screening failed',
          trace_id: task.traceId,
        }, language).message);
        finishTask();
        return;
      }

      if (isRunningScreenTask(task.status)) {
        setAttemptState('running');
        setError('');
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
        return;
      }

      setError(formatUiText(text.unknownTaskStatus, { status: task.status || 'unknown' }));
      setAttemptResult(null);
      setAttemptState('failed');
      finishTask();
    }

    async function pollTask() {
      try {
        const task = await alphasiftApi.getScreenTask(pollingTaskId);
        if (!active) return;
        applyTaskStatus(task);
      } catch (err) {
        if (!active) return;
        const parsedError = getParsedApiError(err, language);
        if (isUnrecoverableScreenTaskError(parsedError)) {
          setError(formatParsedApiError(parsedError) || text.taskUnrecoverable);
          setAttemptResult(null);
          setAttemptState('failed');
          finishTask();
          return;
        }
        setError(formatRecoverableScreenTaskPollingError(parsedError, text));
        setAttemptState('recoverable_poll_error');
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
      }
    }

    void pollTask();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeTaskId, applyScreenResult, language, setExpandedCode, text]);

  const handleStrategyChange = (nextStrategy: string) => {
    if (nextStrategy !== strategy) clearScreeningResults();
    setStrategy(nextStrategy);
  };

  const handleMarketChange = (nextMarket: string) => {
    if (nextMarket !== market) clearScreeningResults();
    setMarket(nextMarket);
  };

  const handleMaxResultsChange = (nextMaxResults: string) => {
    if (nextMaxResults !== String(maxResults)) clearScreeningResults();
    setMaxResultsDraft(nextMaxResults);
    setMaxResultsError('');
  };

  const handleOpenConfiguration = () => {
    setConfigurationError('');
    setConfigurationOpen(true);
  };

  const executeScreen = useCallback(async (
    parameters: ScreeningRunParameters,
  ): Promise<boolean> => {
    lastValidatedParametersRef.current = parameters;
    setAttemptState('submitting');
    setAttemptResult(null);
    setError('');
    setConfigurationError('');
    setTaskProgress(0);
    setTaskMessage(text.submittingTask);
    try {
      const task = await alphasiftApi.startScreen({
        market: parameters.market,
        strategy: parameters.strategy,
        maxResults: parameters.maxResults,
      });
      if (!mountedRef.current) return false;
      persistScreenTask({
        taskId: task.taskId,
        ...parameters,
      });
      setActiveTaskId(task.taskId);
      setAttemptState('running');
      setTaskProgress(0);
      setTaskMessage(formatTaskMessage(task, language));
      return true;
    } catch (submitError) {
      if (mountedRef.current) {
        const message = toApiErrorMessage(submitError, text.taskSubmitFailed, language);
        setAttemptState('failed');
        setConfigurationError(message);
        setError(message);
      }
      return false;
    }
  }, [language, text.submittingTask, text.taskSubmitFailed]);

  const handleSubmit = async (): Promise<boolean> => {
    const parsedMaxResults = Number(maxResultsDraft);
    if (
      !Number.isInteger(parsedMaxResults)
      || parsedMaxResults < 1
      || parsedMaxResults > RESEARCH_DISCOVER_LIMITS.maxCount
    ) {
      setMaxResultsError(text.resultCountError);
      document.getElementById('screening-max-results')?.focus();
      return false;
    }
    setMaxResults(parsedMaxResults);
    setMaxResultsError('');
    return executeScreen({ market, strategy, maxResults: parsedMaxResults });
  };

  const handleRetryScreen = useCallback(() => {
    const parameters = lastValidatedParametersRef.current;
    if (!parameters || capability.state !== 'ready' || loading) return;
    setMarket(parameters.market);
    setStrategy(parameters.strategy);
    setMaxResults(parameters.maxResults);
    setMaxResultsDraft(String(parameters.maxResults));
    void executeScreen(parameters);
  }, [capability.state, executeScreen, loading]);

  const handleConfigurationSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!isScreeningEnabled || loading) return;
    void handleSubmit().then((started) => {
      if (started) setConfigurationOpen(false);
    });
  };

  return (
    <AppPage className="space-y-6 pb-12 pt-6">
      <ScreeningPageHeader text={text} enabled={isScreeningEnabled} status={statusText} />

      <ScreeningPageAlerts
        text={text}
        capability={capability.state}
        capabilityError={capability.error}
        attemptState={attemptState}
        enabling={enabling}
        capabilityActionError={capabilityActionError}
        error={error}
        taskMessage={taskMessage}
        activeTaskId={activeTaskId}
        degradationReasons={degradationReasons}
        attemptResult={attemptResult}
        candidatesCount={candidates.length}
        showingLastGood={showingLastGood}
        canRetryScreen={Boolean(lastValidatedParametersRef.current)}
        onEnable={() => void enableScreening()}
        onOpenDataSources={handleOpenDataSources}
        onRetryStatus={() => void loadStatus()}
        onAdminLogin={handleAdminLogin}
        onRetryScreen={handleRetryScreen}
      />

      <ScreeningHotspotsSection
        text={text}
        language={language}
        isScreeningEnabled={isScreeningEnabled}
        hotspots={hotspots}
        hotspotsUpdatedAt={hotspotsUpdatedAt}
        hotspotsExpanded={hotspotsExpanded}
        selectedHotspotTopic={selectedHotspotTopic}
        hotspotDetail={hotspotDetail}
        loadingHotspots={loadingHotspots}
        loadingHotspotDetail={loadingHotspotDetail}
        hotspotError={hotspotError}
        hotspotDetailError={hotspotDetailError}
        onToggleExpanded={toggleHotspotsExpanded}
        onRefresh={() => void loadHotspots(true)}
        onSelectHotspot={handleHotspotSelect}
        onAnalyzeStock={handleAnalyzeHotspotStock}
      />

      <ScreeningStrategyBar
        text={text}
        strategy={strategy}
        strategyOptions={strategyOptions}
        selectedStrategyTag={selectedStrategyTag}
        strategyDescription={selectedStrategyDisplay?.description || text.strategyDescription}
        strategyLoadError={strategyLoadError}
        loading={loading}
        loadingStrategies={loadingStrategies}
        onStrategyChange={handleStrategyChange}
        onOpenConfiguration={handleOpenConfiguration}
      />

      <ScreeningConfigurationModal
        text={text}
        cancelLabel={t('common.cancel')}
        isOpen={configurationOpen}
        onClose={() => setConfigurationOpen(false)}
        formId={configurationFormId}
        description={selectedStrategyDisplay?.description || text.strategyDescription}
        loading={loading}
        isScreeningEnabled={isScreeningEnabled}
        configurationError={configurationError}
        market={market}
        markets={markets}
        strategy={strategy}
        maxResultsDraft={maxResultsDraft}
        maxResultsError={maxResultsError}
        onSubmit={handleConfigurationSubmit}
        onMarketChange={handleMarketChange}
        onStrategyChange={handleStrategyChange}
        onMaxResultsChange={handleMaxResultsChange}
      />

      <ScreeningRunStatusCard
        text={text}
        loading={loading}
        isScreeningEnabled={isScreeningEnabled}
        statusTitle={runStatusTitle}
        candidatesCount={candidates.length}
        taskMessage={taskMessage}
        taskProgress={taskProgress}
        displayedStrategy={displayedStrategy}
        marketLabel={markets.find((item) => item.id === market)?.label || market}
        activeTaskId={activeTaskId}
        screenMeta={screenMeta}
        showingLastGood={showingLastGood}
      />
      <ScreeningResultsSection
        text={text}
        language={language}
        candidates={candidates}
        expandedCode={expandedCode}
        llmDegraded={llmDegraded}
        emptyState={createScreeningResultsEmptyState({
          text,
          kind: resultsEmptyKind,
          loading,
          onOpenConfiguration: handleOpenConfiguration,
          onOpenDataSources: handleOpenDataSources,
          onRetry: handleRetryScreen,
        })}
        onExpandedCodeChange={handleExpandedCodeChange}
      />
    </AppPage>
  );
};
export default StockScreeningPage;
