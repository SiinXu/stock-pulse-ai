import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PlayCircle } from 'lucide-react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { ApiErrorAlert, Button, ConfirmDialog, InlineAlert, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  DecisionSignalOutcomeRunRequest,
  DecisionSignalOutcomeRunResponse,
} from '../../types/decisionSignals';

// Web-triggered runs use conservative fixed params: only active signals, never
// force-overwrite existing outcomes, and a bounded batch so a click cannot
// recompute everything or hammer data providers.
const SAFE_RUN_PARAMS: DecisionSignalOutcomeRunRequest = {
  status: 'active',
  force: false,
  limit: 100,
};

const RECENT_RUN_LIMIT = 5;

interface RecentRun {
  id: number;
  at: number;
  result: DecisionSignalOutcomeRunResponse;
}

interface DecisionSignalOutcomeRunPanelProps {
  onCompleted: () => void;
}

export const DecisionSignalOutcomeRunPanel: React.FC<DecisionSignalOutcomeRunPanelProps> = ({
  onCompleted,
}) => {
  const { t } = useUiLanguage();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DecisionSignalOutcomeRunResponse | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const runInFlightRef = useRef(false);
  const runSeqRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const summaryText = useCallback(
    (run: DecisionSignalOutcomeRunResponse) => t('decisionSignals.outcomeRun.summary', {
      evaluated: run.evaluated,
      created: run.created,
      updated: run.updated,
      skipped: run.skipped,
    }),
    [t],
  );

  const handleRun = useCallback(async () => {
    if (runInFlightRef.current) return;
    runInFlightRef.current = true;
    const seq = runSeqRef.current + 1;
    runSeqRef.current = seq;
    setConfirmOpen(false);
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await decisionSignalsApi.runOutcomes(SAFE_RUN_PARAMS);
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      setResult(response);
      setRecentRuns((current) => [
        { id: seq, at: Date.now(), result: response },
        ...current,
      ].slice(0, RECENT_RUN_LIMIT));
      onCompleted();
    } catch (err) {
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      setError(getParsedApiError(err));
    } finally {
      if (mountedRef.current && runSeqRef.current === seq) {
        setRunning(false);
      }
      runInFlightRef.current = false;
    }
  }, [onCompleted]);

  return (
    <Surface
      as="section"
      level="interactive"
      padding="sm"
      className="mt-4 space-y-3"
      aria-labelledby="decision-signal-outcome-run"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 id="decision-signal-outcome-run" className="text-sm font-semibold text-foreground">
            {t('decisionSignals.outcomeRun.title')}
          </h3>
          <p className="mt-1 text-xs text-secondary-text">
            {t('decisionSignals.outcomeRun.description')}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="comfortable"
          onClick={() => setConfirmOpen(true)}
          disabled={running}
          isLoading={running}
          loadingText={t('decisionSignals.outcomeRun.running')}
          className="shrink-0"
        >
          <PlayCircle className="h-4 w-4" aria-hidden="true" />
          {t('decisionSignals.outcomeRun.button')}
        </Button>
      </div>

      {running ? (
        <p className="text-xs text-secondary-text" role="status">
          {t('decisionSignals.outcomeRun.running')}
        </p>
      ) : null}

      {error ? (
        <div className="space-y-2">
          <p className="text-sm font-semibold text-danger">{t('decisionSignals.outcomeRun.errorTitle')}</p>
          <ApiErrorAlert error={error} />
        </div>
      ) : null}

      {result ? (
        <InlineAlert
          variant="success"
          title={t('decisionSignals.outcomeRun.resultTitle')}
          message={`${summaryText(result)} · ${t('decisionSignals.outcomeRun.engine', { version: result.engineVersion })}`}
        />
      ) : null}

      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-text">
          {t('decisionSignals.outcomeRun.recentTitle')}
        </h4>
        {recentRuns.length === 0 ? (
          <p className="text-xs text-secondary-text">{t('decisionSignals.outcomeRun.recentEmpty')}</p>
        ) : (
          <ul className="space-y-1">
            {recentRuns.map((run) => (
              <li
                key={run.id}
                className="flex flex-col gap-0.5 rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between"
              >
                <span className="font-mono text-secondary-text">{new Date(run.at).toLocaleString()}</span>
                <span className="text-foreground">{summaryText(run.result)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        title={t('decisionSignals.outcomeRun.confirmTitle')}
        message={t('decisionSignals.outcomeRun.confirmMessage')}
        confirmText={t('common.confirm')}
        confirmDisabled={running}
        cancelDisabled={running}
        onConfirm={() => void handleRun()}
        onCancel={() => setConfirmOpen(false)}
      />
    </Surface>
  );
};
