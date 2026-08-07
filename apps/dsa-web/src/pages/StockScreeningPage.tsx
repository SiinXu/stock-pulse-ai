import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { PlusCircle } from 'lucide-react';
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
import { formatParsedApiError, getParsedApiError, toApiErrorMessage } from '../api/error';
import { AppPage, Button, InlineAlert, Surface } from '../components/common';
import { ScreenAlertMessage } from '../components/screening/ScreenAlertMessage';
import { ScreeningConfigurationModal } from '../components/screening/ScreeningConfigurationModal';
import { ScreeningHotspotsSection } from '../components/screening/ScreeningHotspotsSection';
import { ScreeningResultsSection } from '../components/screening/ScreeningResultsSection';
import { ScreeningRunStatusCard } from '../components/screening/ScreeningRunStatusCard';
import { ScreeningStrategyBar } from '../components/screening/ScreeningStrategyBar';
import { formatHotspotEmptyMessage } from '../components/screening/hotspotModel';
import { getScreenMessages } from '../components/screening/screeningMessages';
import {
  SCREEN_TASK_POLL_INTERVAL_MS,
  clearPersistedScreenTask,
  formatRecoverableScreenTaskPollingError,
  getScreeningRunParametersLocation,
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
} from '../routing/routes';
import {
  DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
} from '../routing/researchRouteState';
import { SCREENING_TEXT } from '../locales/screening';
import { formatTaskMessage } from '../utils/taskMessage';
import { getStrategyDisplay } from '../utils/strategyDisplay';

const StockScreeningPage: React.FC = () => {
  const navigate = useNavigate();
  const syncScreeningRunParameters = useCallback((parameters: ScreeningRunParameters) => {
    const location = getScreeningRunParametersLocation(parameters);
    if (location) navigate(location, { replace: true });
  }, [navigate]);
  const { language, t } = useUiLanguage();
  const configurationFormId = useId();
  const text = SCREENING_TEXT[language];
  const markets = useMemo(
    () => [{ id: RESEARCH_DISCOVER_MARKET_VALUES.china, label: text.marketCn }],
    [text.marketCn],
  );
  const [restoredTask] = useState<PersistedScreenTask | null>(() => readPersistedScreenTask());
  const [initialRunParameters] = useState<ScreeningRunParameters>(() => readScreeningRunParameters(restoredTask));
  const [statusLoading, setStatusLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState(false);
  const [market, setMarket] = useState(initialRunParameters.market);
  const [strategy, setStrategy] = useState(initialRunParameters.strategy);
  const [strategies, setStrategies] = useState<AlphaSiftStrategy[]>([]);
  const [maxResults, setMaxResults] = useState(initialRunParameters.maxResults);
  const [maxResultsDraft, setMaxResultsDraft] = useState(String(initialRunParameters.maxResults));
  const [maxResultsError, setMaxResultsError] = useState('');
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [configurationError, setConfigurationError] = useState('');
  const [candidates, setCandidates] = useState<AlphaSiftCandidate[]>([]);
  const [hotspots, setHotspots] = useState<AlphaSiftHotspot[]>([]);
  const [hotspotsUpdatedAt, setHotspotsUpdatedAt] = useState<string | null>(null);
  const [hotspotsExpanded, setHotspotsExpanded] = useState(false);
  const [selectedHotspotTopic, setSelectedHotspotTopic] = useState<string | null>(null);
  const selectedHotspotTopicRef = useRef<string | null>(null);
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
  const [screenMeta, setScreenMeta] = useState<AlphaSiftScreenResponse | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(restoredTask?.taskId));
  const [enabling, setEnabling] = useState(false);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [error, setError] = useState('');
  const [strategyLoadError, setStrategyLoadError] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(restoredTask?.taskId ?? null);
  const [taskProgress, setTaskProgress] = useState(restoredTask?.taskId ? 10 : 0);
  const [taskMessage, setTaskMessage] = useState(restoredTask?.taskId ? text.restoringTask : '');

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
  const screenMessages = useMemo(() => getScreenMessages(screenMeta, text), [screenMeta, text]);
  const llmDegraded = screenMeta?.llmRanked === false;
  const alertMessages = llmDegraded
    ? screenMessages.length > 0
      ? screenMessages
      : [text.localRankingNotice]
    : screenMessages;
  const isScreeningEnabled = enabled && available;
  const statusText = statusLoading ? text.statusLoading : isScreeningEnabled ? text.enabled : text.disabled;

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  useEffect(() => {
    syncScreeningRunParameters({ market, strategy, maxResults });
  }, [market, maxResults, strategy, syncScreeningRunParameters]);

  const applyScreenResult = useCallback((result: AlphaSiftScreenResponse) => {
    const nextCandidates = result.candidates || [];
    setScreenMeta(result);
    setCandidates(nextCandidates);
    setExpandedCode(nextCandidates[0]?.code ?? null);
  }, []);

  const clearScreeningResults = () => {
    setCandidates([]);
    setScreenMeta(null);
    setExpandedCode(null);
  };

  const loadHotspotDetail = useCallback(async (topic: string, options: { refresh?: boolean } = {}) => {
    if (!topic) {
      return;
    }
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
      if (!canApplyRequest()) {
        return;
      }
      hotspotDetailsByTopicRef.current = {
        ...hotspotDetailsByTopicRef.current,
        [topic]: detail,
      };
      setHotspotDetail(detail);
    } catch (err) {
      if (!canApplyRequest()) {
        return;
      }
      setHotspotDetail(null);
      setHotspotDetailError(toApiErrorMessage(err, text.hotspotDetailLoadFailed, language));
    } finally {
      if (isCurrentRequest()) {
        setLoadingHotspotDetail(false);
      }
    }
  }, [language, text.hotspotDetailLoadFailed]);

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
      hotspotDetailsByTopicRef.current = {
        ...hotspotDetailsByTopicRef.current,
        ...nextDetails,
      };
      const currentTopic = selectedHotspotTopicRef.current;
      const retainedTopic = Boolean(currentTopic && nextHotspots.some((item) => item.topic === currentTopic));
      const nextTopic = retainedTopic ? currentTopic : null;
      setHotspots(nextHotspots);
      setHotspotsUpdatedAt(result.cachedAt || (nextHotspots.length > 0 ? new Date().toISOString() : null));
      setSelectedHotspotTopic(nextTopic);
      selectedHotspotTopicRef.current = nextTopic;
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
  }, [language, loadHotspotDetail, text]);

  const handleHotspotSelect = useCallback((topic: string) => {
    selectedHotspotTopicRef.current = topic;
    setSelectedHotspotTopic(topic);
    const cachedDetail = hotspotDetailsByTopicRef.current[topic];
    if (cachedDetail) {
      setHotspotDetail(cachedDetail);
      setHotspotDetailError('');
      setLoadingHotspotDetail(false);
    } else {
      setHotspotDetail((currentDetail) => (currentDetail?.topic === topic ? currentDetail : null));
    }
  }, []);

  const toggleHotspotsExpanded = useCallback(() => {
    setHotspotsExpanded((expanded) => {
      const nextExpanded = !expanded;
      if (!nextExpanded) {
        selectedHotspotTopicRef.current = null;
        setSelectedHotspotTopic(null);
        setHotspotDetail(null);
        setHotspotDetailError('');
      }
      return nextExpanded;
    });
  }, []);

  const handleAnalyzeHotspotStock = useCallback((stock: AlphaSiftHotspotDetail['stocks'][number]) => {
    const stockCode = String(stock.code || '').trim();
    if (!stockCode) {
      return;
    }
    const stockName = String(stock.name || stockCode).trim();
    navigate('/', {
      state: {
        stockCode,
        stockName,
        autoAnalyze: true,
        selectionSource: 'alphasift_hotspot',
      },
    });
  }, [navigate]);

  useEffect(() => {
    selectedHotspotTopicRef.current = selectedHotspotTopic;
  }, [selectedHotspotTopic]);

  useEffect(() => {
    if (!selectedHotspotTopic) {
      return;
    }
    void loadHotspotDetail(selectedHotspotTopic);
  }, [loadHotspotDetail, selectedHotspotTopic]);

  useEffect(() => {
    let active = true;
    alphasiftApi
      .getStatus()
      .then((status) => {
        if (!active) {
          return;
        }
        setEnabled(status.enabled);
        setAvailable(status.available);
        setStatusLoading(false);
        if (status.enabled && status.available) {
          void loadStrategies();
          void loadHotspots(false);
        }
      })
      .catch(() => {
        if (active) {
          setEnabled(false);
          setAvailable(false);
          setStatusLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadHotspots, loadStrategies]);

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
    if (!activeTaskId) {
      return undefined;
    }

    const pollingTaskId = activeTaskId;
    let active = true;
    let timer: number | undefined;

    function finishTask() {
      clearPersistedScreenTask();
      setActiveTaskId(null);
      setLoading(false);
    }

    function applyTaskStatus(task: AlphaSiftScreenTaskStatus) {
      const nextProgress = Number(task.progress ?? 0);
      setTaskProgress(Number.isFinite(nextProgress) ? nextProgress : 0);
      setTaskMessage(formatTaskMessage(task, language));

      if (task.status === 'completed') {
        if (task.result) {
          applyScreenResult(task.result);
          setError('');
        } else {
          setError(text.noTaskResults);
          setCandidates([]);
          setScreenMeta(null);
        }
        finishTask();
        return;
      }

      if (task.status === 'failed') {
        setCandidates([]);
        setScreenMeta(null);
        setExpandedCode(null);
        setError(getParsedApiError({
          error: 'alphasift_screen_failed',
          message: task.error || task.message || 'Screening failed',
          trace_id: task.traceId,
        }, language).message);
        finishTask();
        return;
      }

      if (isRunningScreenTask(task.status)) {
        setLoading(true);
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
        return;
      }

      setError(formatUiText(text.unknownTaskStatus, { status: task.status || 'unknown' }));
      finishTask();
    }

    async function pollTask() {
      try {
        const task = await alphasiftApi.getScreenTask(pollingTaskId);
        if (!active) {
          return;
        }
        applyTaskStatus(task);
      } catch (err) {
        if (!active) {
          return;
        }
        const parsedError = getParsedApiError(err, language);
        if (isUnrecoverableScreenTaskError(parsedError)) {
          setError(formatParsedApiError(parsedError) || text.taskUnrecoverable);
          setCandidates([]);
          setScreenMeta(null);
          finishTask();
          return;
        }
        setError(formatRecoverableScreenTaskPollingError(parsedError, text));
        setLoading(true);
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
      }
    }

    void pollTask();

    return () => {
      active = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [activeTaskId, applyScreenResult, language, text]);

  const handleEnable = async () => {
    setEnabling(true);
    setError('');
    try {
      await alphasiftApi.enable();
      if (!mountedRef.current) return;
      setEnabled(true);
      setAvailable(true);
      setStatusLoading(false);
      await loadStrategies();
    } catch (err) {
      try {
        const status = await alphasiftApi.getStatus();
        if (!mountedRef.current) return;
        setEnabled(status.enabled);
        setAvailable(status.available);
        setStatusLoading(false);
      } catch {
        if (!mountedRef.current) return;
        setEnabled(false);
        setAvailable(false);
        setStatusLoading(false);
      }
      if (mountedRef.current) setError(getParsedApiError(err, language).message || text.enableFailed);
    } finally {
      if (mountedRef.current) setEnabling(false);
    }
  };

  const handleStrategyChange = (nextStrategy: string) => {
    if (nextStrategy !== strategy) {
      clearScreeningResults();
    }
    setStrategy(nextStrategy);
  };

  const handleMarketChange = (nextMarket: string) => {
    if (nextMarket !== market) {
      clearScreeningResults();
    }
    setMarket(nextMarket);
  };

  const handleMaxResultsChange = (nextMaxResults: string) => {
    if (nextMaxResults !== String(maxResults)) {
      clearScreeningResults();
    }
    setMaxResultsDraft(nextMaxResults);
    setMaxResultsError('');
  };

  const handleOpenConfiguration = () => {
    setConfigurationError('');
    setConfigurationOpen(true);
  };

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
    setConfigurationError('');
    setLoading(true);
    setError('');
    setScreenMeta(null);
    setTaskProgress(0);
    setTaskMessage(text.submittingTask);
    try {
      const task = await alphasiftApi.startScreen({ market, strategy, maxResults: parsedMaxResults });
      if (!mountedRef.current) return false;
      persistScreenTask({
        taskId: task.taskId,
        market,
        strategy,
        maxResults: parsedMaxResults,
      });
      setActiveTaskId(task.taskId);
      setTaskProgress(0);
      setTaskMessage(formatTaskMessage(task, language));
      return true;
    } catch (err) {
      if (mountedRef.current) {
        const message = toApiErrorMessage(err, text.taskSubmitFailed, language);
        setCandidates([]);
        setLoading(false);
        setConfigurationError(message);
        setError(message);
      }
      return false;
    }
  };

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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-primary text-primary shadow-soft-card">
            <PlusCircle className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-normal text-foreground">{text.title}</h1>
            <p className="mt-1 text-sm text-secondary-text">{text.description}</p>
          </div>
        </div>

        <Surface level="interactive" className="inline-flex w-fit items-center gap-2 px-3 py-2 text-sm">
          <span className={`h-2.5 w-2.5 rounded-full ${isScreeningEnabled ? 'bg-success' : 'bg-warning'}`} />
          <span className="font-medium text-secondary-text">{statusText}</span>
        </Surface>
      </div>

      {!statusLoading && !enabled ? (
        <InlineAlert
          variant="info"
          title={text.notEnabledTitle}
          message={text.notEnabledMessage}
          action={
            <Button variant="primary" size="default" isLoading={enabling} loadingText={text.enabling} onClick={() => void handleEnable()}>
              {text.enable}
            </Button>
          }
        />
      ) : null}

      {!statusLoading && enabled && !available ? (
        <InlineAlert
          variant="warning"
          title={text.unavailableTitle}
          message={text.unavailableMessage}
        />
      ) : null}

      <InlineAlert
        variant="warning"
        title={text.riskTitle}
        message={text.riskMessage}
      />

      {loading ? (
        <InlineAlert
          variant="info"
          title={text.taskRunningTitle}
          message={`${taskMessage || text.runningTask}. ${text.taskId}: ${activeTaskId ? activeTaskId.slice(0, 12) : '-'}`}
        />
      ) : null}

      {error ? <InlineAlert variant="danger" title={text.callFailed} message={error} /> : null}

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
        candidatesCount={candidates.length}
        taskMessage={taskMessage}
        taskProgress={taskProgress}
        displayedStrategy={displayedStrategy}
        marketLabel={markets.find((item) => item.id === market)?.label || market}
        activeTaskId={activeTaskId}
        screenMeta={screenMeta}
      />

      {screenMeta && alertMessages.length > 0 ? (
        <InlineAlert
          variant={llmDegraded ? 'warning' : 'info'}
          title={llmDegraded ? text.llmDegraded : text.alphaSiftNotice}
          message={<ScreenAlertMessage messages={alertMessages} />}
        />
      ) : null}

      <ScreeningResultsSection
        text={text}
        language={language}
        candidates={candidates}
        expandedCode={expandedCode}
        llmDegraded={llmDegraded}
        loading={loading}
        onExpandedCodeChange={setExpandedCode}
        onOpenConfiguration={handleOpenConfiguration}
      />
    </AppPage>
  );
};



export default StockScreeningPage;
