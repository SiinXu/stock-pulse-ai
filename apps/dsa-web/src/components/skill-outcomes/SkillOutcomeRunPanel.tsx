// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PlayCircle } from 'lucide-react';
import { skillOutcomesApi, type SkillOutcomeRunResponse } from '../../api/skillOutcomes';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { SKILL_OUTCOMES_TEXT } from '../../locales/skillOutcomes';
import {
  ApiErrorAlert,
  Button,
  ConfirmDialog,
  InlineAlert,
  Surface,
} from '../common';

const SAFE_RUN_LIMIT = 100;

export interface SkillOutcomeRunPanelProps {
  onCompleted: () => void;
  disabled?: boolean;
}

export const SkillOutcomeRunPanel: React.FC<SkillOutcomeRunPanelProps> = ({
  onCompleted,
  disabled = false,
}) => {
  const { language } = useUiLanguage();
  const text = SKILL_OUTCOMES_TEXT[language];
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SkillOutcomeRunResponse | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
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
    (run: SkillOutcomeRunResponse) => formatUiText(text.runSummary, {
      processed: run.processedKeys,
      created: run.created,
      updated: run.updated,
      skipped: run.skipped,
      failed: run.failed,
      histories: run.historiesScanned,
      samples: run.samplesCreated,
    }),
    [text.runSummary],
  );

  const handleRun = useCallback(async () => {
    if (runInFlightRef.current || disabled) return;
    runInFlightRef.current = true;
    const seq = runSeqRef.current + 1;
    runSeqRef.current = seq;
    setConfirmOpen(false);
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await skillOutcomesApi.runOutcomes({ limit: SAFE_RUN_LIMIT });
      if (!mountedRef.current || runSeqRef.current !== seq) return;
      setResult(response);
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
  }, [disabled, onCompleted]);

  return (
    <Surface
      as="section"
      level="interactive"
      padding="sm"
      className="space-y-3"
      aria-labelledby="skill-outcome-run"
      data-testid="skill-outcome-run-panel"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 id="skill-outcome-run" className="text-sm font-semibold text-foreground">
            {text.runTitle}
          </h3>
          <p className="mt-1 text-xs text-secondary-text">{text.runDescription}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="comfortable"
          onClick={() => setConfirmOpen(true)}
          disabled={disabled || running}
          isLoading={running}
          loadingText={text.runRunning}
          className="shrink-0"
        >
          <PlayCircle className="h-4 w-4" aria-hidden="true" />
          {text.runButton}
        </Button>
      </div>

      {running ? (
        <p className="text-xs text-secondary-text" role="status">
          {text.runRunning}
        </p>
      ) : null}

      {error ? (
        <div className="space-y-2" data-testid="skill-outcome-run-error">
          <p className="text-sm font-semibold text-danger">{text.runErrorTitle}</p>
          <ApiErrorAlert error={error} />
        </div>
      ) : null}

      {result ? (
        <InlineAlert
          variant="success"
          title={text.runResultTitle}
          message={summaryText(result)}
          data-testid="skill-outcome-run-result"
        />
      ) : null}

      <ConfirmDialog
        isOpen={confirmOpen}
        title={text.runConfirmTitle}
        message={text.runConfirmMessage}
        confirmText={text.runButton}
        confirmDisabled={running}
        cancelDisabled={running}
        onConfirm={() => void handleRun()}
        onCancel={() => setConfirmOpen(false)}
      />
    </Surface>
  );
};
