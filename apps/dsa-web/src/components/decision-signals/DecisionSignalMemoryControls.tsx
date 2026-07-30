// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { DECISION_SIGNAL_WORKSTREAM_TEXT } from '../../locales/decisionSignals';
import type {
  DecisionSignalMemoryFlagItem,
  DecisionSignalMemoryFlagUpdateRequest,
} from '../../types/decisionSignals';
import {
  ApiErrorAlert,
  Badge,
  InlineAlert,
  Section,
  Spinner,
  Switch,
} from '../common';

export interface DecisionSignalMemoryControlsProps {
  signalId: number;
}

type MemoryFlagKey = keyof Pick<DecisionSignalMemoryFlagItem, 'memorable' | 'ignored'>;

interface FailedMemorySave {
  signalId: number;
  payload: DecisionSignalMemoryFlagUpdateRequest;
}

export const DecisionSignalMemoryControls: React.FC<DecisionSignalMemoryControlsProps> = ({
  signalId,
}) => {
  const { language, t } = useUiLanguage();
  const text = DECISION_SIGNAL_WORKSTREAM_TEXT[language];
  const [flags, setFlags] = useState<DecisionSignalMemoryFlagItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [errorKind, setErrorKind] = useState<'load' | 'save'>('load');
  const [failedSave, setFailedSave] = useState<FailedMemorySave | null>(null);
  const operationEpochRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const currentFlags = flags?.signalId === signalId ? flags : null;

  const loadFlags = useCallback(async () => {
    const epoch = operationEpochRef.current + 1;
    operationEpochRef.current = epoch;
    saveInFlightRef.current = false;
    setLoading(true);
    setSaving(false);
    setError(null);
    setErrorKind('load');
    setFailedSave(null);
    try {
      const response = await decisionSignalsApi.getMemoryFlag(signalId);
      if (operationEpochRef.current !== epoch) return;
      if (response.signalId !== signalId) {
        throw new Error('Decision-memory response signal ID mismatch');
      }
      setFlags(response);
    } catch (requestError) {
      if (operationEpochRef.current !== epoch) return;
      setFlags(null);
      setError(getParsedApiError(requestError));
    } finally {
      if (operationEpochRef.current === epoch) setLoading(false);
    }
  }, [signalId]);

  useEffect(() => {
    setFlags(null);
    setFailedSave(null);
    void loadFlags();
    return () => {
      operationEpochRef.current += 1;
      saveInFlightRef.current = false;
    };
  }, [loadFlags]);

  const saveFlags = useCallback(async (
    targetSignalId: number,
    payload: DecisionSignalMemoryFlagUpdateRequest,
  ) => {
    if (targetSignalId !== signalId || saveInFlightRef.current) return;
    const epoch = operationEpochRef.current;
    saveInFlightRef.current = true;
    setSaving(true);
    setError(null);
    setErrorKind('save');
    setFailedSave(null);
    try {
      const response = await decisionSignalsApi.updateMemoryFlag(targetSignalId, payload);
      if (operationEpochRef.current !== epoch) return;
      if (response.signalId !== targetSignalId) {
        throw new Error('Decision-memory response signal ID mismatch');
      }
      setFlags(response);
    } catch (requestError) {
      if (operationEpochRef.current !== epoch) return;
      setError(getParsedApiError(requestError));
      setFailedSave({ signalId: targetSignalId, payload });
    } finally {
      if (operationEpochRef.current === epoch) {
        saveInFlightRef.current = false;
        setSaving(false);
      }
    }
  }, [signalId]);

  const updateFlag = useCallback((key: MemoryFlagKey, nextValue: boolean) => {
    if (!currentFlags || loading || saveInFlightRef.current) return;
    const payload: DecisionSignalMemoryFlagUpdateRequest = key === 'memorable'
      ? { memorable: nextValue }
      : { ignored: nextValue };
    void saveFlags(signalId, payload);
  }, [currentFlags, loading, saveFlags, signalId]);

  const retryFailedSave = useCallback(() => {
    if (!failedSave || failedSave.signalId !== signalId) return;
    void saveFlags(failedSave.signalId, failedSave.payload);
  }, [failedSave, saveFlags, signalId]);

  const controlsDisabled = loading || saving || currentFlags === null;
  const errorTitle = errorKind === 'load'
    ? text.memoryLoadErrorTitle
    : text.memorySaveErrorTitle;
  const canRetrySave = errorKind === 'save' && failedSave?.signalId === signalId;

  return (
    <Section
      title={text.memoryTitle}
      description={text.memoryDescription}
      headingAs="h3"
      level="section"
      padding="sm"
      actions={(
        <div className="flex flex-wrap gap-2">
          {currentFlags?.memorable ? (
            <Badge variant="info">{text.memoryMemorable}</Badge>
          ) : null}
          {currentFlags?.ignored ? (
            <Badge variant="warning">{text.memoryIgnored}</Badge>
          ) : null}
          {currentFlags && !currentFlags.memorable && !currentFlags.ignored ? (
            <Badge variant="default">{text.memoryDefault}</Badge>
          ) : null}
        </div>
      )}
    >
      <div className="space-y-3" aria-busy={loading || saving || undefined}>
        {loading || saving ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 text-sm text-secondary-text"
          >
            <Spinner size="sm" />
            <span>
              {loading ? t('common.loading') : t('decisionSignals.reassessPersisting')}
            </span>
          </div>
        ) : null}
        {error ? (
          <ApiErrorAlert
            error={{ ...error, title: errorTitle }}
            actionLabel={t('common.retry')}
            onAction={canRetrySave ? retryFailedSave : () => void loadFlags()}
          />
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                {text.memoryMemorable}
              </p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {text.memoryMemorableDescription}
              </p>
            </div>
            <Switch
              checked={currentFlags?.memorable ?? false}
              disabled={controlsDisabled}
              aria-label={text.memoryMemorable}
              onCheckedChange={(next) => void updateFlag('memorable', next)}
            />
          </div>
          <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                {text.memoryIgnored}
              </p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {text.memoryIgnoredDescription}
              </p>
            </div>
            <Switch
              checked={currentFlags?.ignored ?? false}
              disabled={controlsDisabled}
              aria-label={text.memoryIgnored}
              onCheckedChange={(next) => void updateFlag('ignored', next)}
            />
          </div>
        </div>
        {currentFlags?.memorable && currentFlags.ignored ? (
          <InlineAlert
            variant="warning"
            message={text.memoryIgnoredPrecedence}
          />
        ) : null}
      </div>
    </Section>
  );
};
