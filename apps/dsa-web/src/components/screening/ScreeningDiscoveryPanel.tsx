// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  candidateDiscoveryApi,
  type CandidateDiscoveryResponse,
  type DiscoveryCandidate,
  type DiscoveryUniverse,
} from '../../api/candidateDiscovery';
import { toApiErrorMessage } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { buildDeepLink } from '../../utils/deepLink';
import { formatSignedChangePercent } from '../../utils/marketFormat';
import { Button, DataTable, Input, Select, Surface, Textarea, type DataTableColumn } from '../common';
import { SignedChangeText } from '../theme/SignedChangeText';
import type { DiscoveryScreeningText } from './screeningText';

const POLL_MS = 1500;

export type ScreeningDiscoveryPanelProps = {
  text: DiscoveryScreeningText;
};

type RunState = 'idle' | 'submitting' | 'running' | 'completed' | 'failed' | 'cancelled';

const ScreeningDiscoveryPanel: React.FC<ScreeningDiscoveryPanelProps> = ({ text }) => {
  const navigate = useNavigate();
  const { language } = useUiLanguage();
  const mountedRef = useRef(true);
  const [query, setQuery] = useState('');
  const [universe, setUniverse] = useState<DiscoveryUniverse>('watchlist');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [maxResults, setMaxResults] = useState(10);
  const [maxProviderCalls, setMaxProviderCalls] = useState(20);
  const [runState, setRunState] = useState<RunState>('idle');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState<CandidateDiscoveryResponse | null>(null);
  const [watchlistBusy, setWatchlistBusy] = useState<string | null>(null);
  const [watchlistNotice, setWatchlistNotice] = useState('');

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const universeOptions = useMemo(
    () => [
      { value: 'watchlist', label: text.discoveryUniverseWatchlist },
      { value: 'portfolio', label: text.discoveryUniversePortfolio },
      { value: 'index', label: text.discoveryUniverseIndex },
    ],
    [text.discoveryUniverseIndex, text.discoveryUniversePortfolio, text.discoveryUniverseWatchlist],
  );

  const loading = runState === 'submitting' || runState === 'running';
  const pollTimerRef = useRef<number | null>(null);
  const pollGenerationRef = useRef(0);

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current != null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => {
    pollGenerationRef.current += 1;
    clearPollTimer();
  }, [clearPollTimer]);

  const pollTask = useCallback(async (id: string, generation: number) => {
    if (!mountedRef.current || generation !== pollGenerationRef.current) return;
    try {
      const task = await candidateDiscoveryApi.getTask(id);
      if (!mountedRef.current || generation !== pollGenerationRef.current) return;
      setProgress(Number(task.progress ?? 0));
      setMessage(task.message || '');
      if (task.status === 'completed') {
        setResult(task.result ?? null);
        setRunState('completed');
        setTaskId(null);
        return;
      }
      if (task.status === 'failed') {
        setError(task.error || task.message || text.discoveryFailed);
        setRunState('failed');
        setTaskId(null);
        return;
      }
      if (task.status === 'cancelled' || task.status === 'cancel_requested') {
        setMessage(task.message || text.discoveryCancelRequested);
        if (task.status === 'cancelled') {
          setRunState('cancelled');
          setTaskId(null);
          return;
        }
        setRunState('running');
      } else {
        setRunState('running');
      }
      clearPollTimer();
      pollTimerRef.current = window.setTimeout(() => {
        void pollTask(id, generation);
      }, POLL_MS);
    } catch (err) {
      if (!mountedRef.current || generation !== pollGenerationRef.current) return;
      setError(toApiErrorMessage(err, text.discoveryFailed, language));
      setRunState('failed');
      setTaskId(null);
    }
  }, [clearPollTimer, language, text.discoveryCancelRequested, text.discoveryFailed]);

  const handleRun = async () => {
    setError('');
    setWatchlistNotice('');
    setRunState('submitting');
    setProgress(0);
    setMessage(text.discoverySubmitting);
    clearPollTimer();
    pollGenerationRef.current += 1;
    const generation = pollGenerationRef.current;
    try {
      const accepted = await candidateDiscoveryApi.startTask({
        query: query.trim(),
        universe,
        page,
        pageSize,
        maxResults,
        maxProviderCalls,
        language: language.startsWith('zh') ? 'zh' : 'en',
      });
      if (!mountedRef.current || generation !== pollGenerationRef.current) return;
      setTaskId(accepted.taskId);
      setRunState('running');
      setMessage(accepted.message || text.discoveryRunning);
      void pollTask(accepted.taskId, generation);
    } catch (err) {
      if (!mountedRef.current || generation !== pollGenerationRef.current) return;
      setError(toApiErrorMessage(err, text.discoveryFailed, language));
      setRunState('failed');
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await candidateDiscoveryApi.cancelTask(taskId);
      if (mountedRef.current) {
        setMessage(text.discoveryCancelRequested);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(toApiErrorMessage(err, text.discoveryCancelFailed, language));
      }
    }
  };

  const handleAnalyze = (candidate: DiscoveryCandidate) => {
    try {
      navigate(buildDeepLink({ page: 'home', stockCode: candidate.code }));
    } catch {
      navigate(`/?stock=${encodeURIComponent(candidate.code)}`);
    }
  };

  const handleAddWatchlist = async (candidate: DiscoveryCandidate) => {
    setWatchlistBusy(candidate.code);
    setWatchlistNotice('');
    try {
      await systemConfigApi.addToWatchlist(candidate.code);
      if (mountedRef.current) {
        setWatchlistNotice(formatUiText(text.discoveryWatchlistAdded, { code: candidate.code }));
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(toApiErrorMessage(err, text.discoveryWatchlistFailed, language));
      }
    } finally {
      if (mountedRef.current) setWatchlistBusy(null);
    }
  };

  const candidates = result?.candidates ?? [];
  const cost = result?.costContract ?? {};
  const universeContract = result?.universeContract ?? {};
  const candidateColumns: readonly DataTableColumn<DiscoveryCandidate>[] = [
    { id: 'rank', header: '#', width: 'compact', cell: (item) => item.rank },
    {
      id: 'code',
      header: text.code,
      rowHeader: true,
      nowrap: true,
      cell: (item) => <span className="font-mono font-semibold">{item.code}</span>,
    },
    { id: 'name', header: text.name, cell: (item) => item.name },
    { id: 'score', header: text.score, cell: (item) => item.score ?? '-' },
    {
      id: 'change',
      header: text.change,
      cell: (item) => {
        if (item.changePct == null || !Number.isFinite(Number(item.changePct))) return '-';
        const changePct = Number(item.changePct);
        return (
          <SignedChangeText value={changePct} market={item.code}>
            {formatSignedChangePercent(changePct)}
          </SignedChangeText>
        );
      },
    },
    {
      id: 'summary',
      header: text.summary,
      width: 'wide',
      cell: (item) => <span className="leading-5 text-secondary-text">{item.reason}</span>,
    },
    {
      id: 'actions',
      header: text.details,
      cell: (item) => (
        <div className="flex flex-col gap-1">
          <Button type="button" size="compact" variant="secondary" onClick={() => handleAnalyze(item)}>
            {text.analyze}
          </Button>
          <Button
            type="button"
            size="compact"
            variant="ghost"
            disabled={watchlistBusy === item.code}
            onClick={() => void handleAddWatchlist(item)}
          >
            {text.discoveryAddWatchlist}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Surface as="section" level="interactive" padding="none" className="space-y-4 p-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{text.discoveryTitle}</h2>
        <p className="mt-1 text-xs text-secondary-text">{text.discoveryDescription}</p>
        <p className="mt-2 text-xs text-secondary-text">{text.discoveryDisclaimer}</p>
      </div>

      <Textarea
        label={text.discoveryQuery}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        rows={3}
        maxLength={500}
        disabled={loading}
        placeholder={text.discoveryQueryPlaceholder}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Select
          label={text.discoveryUniverse}
          value={universe}
          onChange={(value) => setUniverse(value as DiscoveryUniverse)}
          options={universeOptions}
          disabled={loading}
          ariaLabel={text.discoveryUniverse}
          className="w-full [&>div]:w-full"
        />
        <Input
          label={text.discoveryPage}
          type="number"
          min={1}
          value={page}
          disabled={loading}
          onChange={(event) => setPage(Math.max(1, Number(event.target.value) || 1))}
        />
        <Input
          label={text.discoveryPageSize}
          type="number"
          min={1}
          max={100}
          value={pageSize}
          disabled={loading}
          onChange={(event) => setPageSize(Math.min(100, Math.max(1, Number(event.target.value) || 50)))}
        />
        <Input
          label={text.discoveryMaxResults}
          type="number"
          min={1}
          max={30}
          value={maxResults}
          disabled={loading}
          onChange={(event) => setMaxResults(Math.min(30, Math.max(1, Number(event.target.value) || 10)))}
        />
      </div>

      <Input
        fieldClassName="max-w-xs"
        label={text.discoveryProviderBudget}
        type="number"
        min={0}
        max={50}
        value={maxProviderCalls}
        disabled={loading}
        onChange={(event) => setMaxProviderCalls(Math.min(50, Math.max(0, Number(event.target.value) || 0)))}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="primary" onClick={() => void handleRun()} disabled={loading}>
          {loading ? text.discoveryRunning : text.discoveryRun}
        </Button>
        {loading && taskId ? (
          <Button type="button" variant="secondary" onClick={() => void handleCancel()}>
            {text.discoveryCancel}
          </Button>
        ) : null}
        {loading ? (
          <span className="text-xs text-secondary-text">
            {formatUiText(text.discoveryProgress, { progress: String(progress), message: message || text.discoveryRunning })}
          </span>
        ) : null}
      </div>

      {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
      {watchlistNotice ? <p className="text-xs text-success">{watchlistNotice}</p> : null}

      {result ? (
        <div className="space-y-3 rounded-lg border border-border/70 bg-background/60 p-3">
          <div className="flex flex-wrap gap-3 text-xs text-secondary-text">
            <span>
              {formatUiText(text.discoveryCostSummary, {
                provider: String(cost.provider_calls ?? cost.providerCalls ?? 0),
                maxProvider: String(cost.max_provider_calls ?? cost.maxProviderCalls ?? 0),
                candidates: String(result.candidateCount),
              })}
            </span>
            <span>
              {formatUiText(text.discoveryUniverseSummary, {
                source: String(universeContract.source ?? result.universe),
                resolved: String(universeContract.resolved_count ?? universeContract.resolvedCount ?? 0),
                evaluated: String(universeContract.evaluated_count ?? universeContract.evaluatedCount ?? 0),
              })}
            </span>
          </div>
          {(result.warnings || []).length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-secondary-text">
              {result.warnings?.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          {candidates.length === 0 ? (
            <p className="text-sm text-secondary-text">
              {result.emptyMessage || text.discoveryNoHits}
            </p>
          ) : (
            <DataTable
              caption={text.discoveryTitle}
              columns={candidateColumns}
              rows={candidates}
              getRowKey={(item) => `${item.rank}-${item.code}`}
              emptyState={{ title: text.discoveryNoHits }}
              density="compact"
              frame="embedded"
              minWidth="wide"
              virtualization={false}
            />
          )}
          <p className="text-xs text-secondary-text">{result.researchDisclaimer || text.discoveryDisclaimer}</p>
        </div>
      ) : null}
    </Surface>
  );
};

export default ScreeningDiscoveryPanel;
