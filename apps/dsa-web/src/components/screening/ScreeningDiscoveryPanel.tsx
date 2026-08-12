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
import { Button, Select, Surface } from '../common';
import type { ScreeningText } from './screeningText';

const POLL_MS = 1500;

export type ScreeningDiscoveryPanelProps = {
  text: ScreeningText;
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

  const pollTask = useCallback(async (id: string) => {
    try {
      const task = await candidateDiscoveryApi.getTask(id);
      if (!mountedRef.current) return;
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
        setRunState(task.status === 'cancelled' ? 'cancelled' : 'running');
        setMessage(task.message || text.discoveryCancelRequested);
        if (task.status === 'cancelled') {
          setTaskId(null);
          return;
        }
      } else {
        setRunState('running');
      }
      window.setTimeout(() => {
        void pollTask(id);
      }, POLL_MS);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(toApiErrorMessage(err, text.discoveryFailed, language));
      setRunState('failed');
      setTaskId(null);
    }
  }, [language, text.discoveryCancelRequested, text.discoveryFailed]);

  const handleRun = async () => {
    setError('');
    setWatchlistNotice('');
    setRunState('submitting');
    setProgress(0);
    setMessage(text.discoverySubmitting);
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
      if (!mountedRef.current) return;
      setTaskId(accepted.taskId);
      setRunState('running');
      setMessage(accepted.message || text.discoveryRunning);
      void pollTask(accepted.taskId);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(toApiErrorMessage(err, text.discoveryFailed, language));
      setRunState('failed');
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await candidateDiscoveryApi.cancelTask(taskId);
      setMessage(text.discoveryCancelRequested);
    } catch (err) {
      setError(toApiErrorMessage(err, text.discoveryCancelFailed, language));
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

  return (
    <Surface as="section" level="interactive" padding="none" className="space-y-4 p-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{text.discoveryTitle}</h2>
        <p className="mt-1 text-xs text-secondary-text">{text.discoveryDescription}</p>
        <p className="mt-2 text-xs text-secondary-text">{text.discoveryDisclaimer}</p>
      </div>

      <label className="block space-y-1">
        <span className="text-xs font-semibold text-secondary-text">{text.discoveryQuery}</span>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          rows={3}
          maxLength={500}
          disabled={loading}
          placeholder={text.discoveryQueryPlaceholder}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
        />
      </label>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs font-semibold text-secondary-text">{text.discoveryUniverse}</span>
          <Select
            value={universe}
            onChange={(value) => setUniverse(value as DiscoveryUniverse)}
            options={universeOptions}
            disabled={loading}
            ariaLabel={text.discoveryUniverse}
            className="w-full [&>div]:w-full"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-semibold text-secondary-text">{text.discoveryPage}</span>
          <input
            type="number"
            min={1}
            value={page}
            disabled={loading}
            onChange={(event) => setPage(Math.max(1, Number(event.target.value) || 1))}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-semibold text-secondary-text">{text.discoveryPageSize}</span>
          <input
            type="number"
            min={1}
            max={100}
            value={pageSize}
            disabled={loading}
            onChange={(event) => setPageSize(Math.min(100, Math.max(1, Number(event.target.value) || 50)))}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-semibold text-secondary-text">{text.discoveryMaxResults}</span>
          <input
            type="number"
            min={1}
            max={30}
            value={maxResults}
            disabled={loading}
            onChange={(event) => setMaxResults(Math.min(30, Math.max(1, Number(event.target.value) || 10)))}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
        </label>
      </div>

      <label className="block max-w-xs space-y-1">
        <span className="text-xs font-semibold text-secondary-text">{text.discoveryProviderBudget}</span>
        <input
          type="number"
          min={0}
          max={50}
          value={maxProviderCalls}
          disabled={loading}
          onChange={(event) => setMaxProviderCalls(Math.min(50, Math.max(0, Number(event.target.value) || 0)))}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </label>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={() => void handleRun()} disabled={loading}>
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
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs text-secondary-text">
                  <tr>
                    <th className="px-2 py-1">#</th>
                    <th className="px-2 py-1">{text.code}</th>
                    <th className="px-2 py-1">{text.name}</th>
                    <th className="px-2 py-1">{text.score}</th>
                    <th className="px-2 py-1">{text.change}</th>
                    <th className="px-2 py-1">{text.summary}</th>
                    <th className="px-2 py-1">{text.details}</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((item) => (
                    <tr key={`${item.rank}-${item.code}`} className="border-t border-border/50 align-top">
                      <td className="px-2 py-2">{item.rank}</td>
                      <td className="px-2 py-2 font-mono font-semibold">{item.code}</td>
                      <td className="px-2 py-2">{item.name}</td>
                      <td className="px-2 py-2">{item.score ?? '-'}</td>
                      <td className="px-2 py-2">
                        {item.changePct == null ? '-' : `${Number(item.changePct).toFixed(2)}%`}
                      </td>
                      <td className="px-2 py-2 text-xs leading-5 text-secondary-text">{item.reason}</td>
                      <td className="px-2 py-2">
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
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-secondary-text">{result.researchDisclaimer || text.discoveryDisclaimer}</p>
        </div>
      ) : null}
    </Surface>
  );
};

export default ScreeningDiscoveryPanel;
