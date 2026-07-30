// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  DecisionSignalMemoryFlagItem,
  DecisionSignalMemoryFlagUpdateRequest,
} from '../../types/decisionSignals';
import {
  ApiErrorAlert,
  Badge,
  InlineAlert,
  Section,
  Switch,
} from '../common';

export interface DecisionSignalMemoryControlsProps {
  signalId: number;
}

type MemoryFlagKey = keyof Pick<DecisionSignalMemoryFlagItem, 'memorable' | 'ignored'>;

export const DecisionSignalMemoryControls: React.FC<DecisionSignalMemoryControlsProps> = ({
  signalId,
}) => {
  const { t } = useUiLanguage();
  const [flags, setFlags] = useState<DecisionSignalMemoryFlagItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [errorKind, setErrorKind] = useState<'load' | 'save'>('load');
  const operationEpochRef = useRef(0);
  const saveInFlightRef = useRef(false);

  const loadFlags = useCallback(async () => {
    const epoch = operationEpochRef.current + 1;
    operationEpochRef.current = epoch;
    saveInFlightRef.current = false;
    setLoading(true);
    setSaving(false);
    setError(null);
    setErrorKind('load');
    try {
      const response = await decisionSignalsApi.getMemoryFlag(signalId);
      if (operationEpochRef.current !== epoch) return;
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
    void loadFlags();
    return () => {
      operationEpochRef.current += 1;
      saveInFlightRef.current = false;
    };
  }, [loadFlags]);

  const updateFlag = useCallback(async (key: MemoryFlagKey, nextValue: boolean) => {
    if (!flags || loading || saveInFlightRef.current) return;
    const epoch = operationEpochRef.current;
    const payload: DecisionSignalMemoryFlagUpdateRequest = key === 'memorable'
      ? { memorable: nextValue }
      : { ignored: nextValue };
    saveInFlightRef.current = true;
    setSaving(true);
    setError(null);
    setErrorKind('save');
    try {
      const response = await decisionSignalsApi.updateMemoryFlag(signalId, payload);
      if (operationEpochRef.current !== epoch) return;
      setFlags(response);
    } catch (requestError) {
      if (operationEpochRef.current !== epoch) return;
      setError(getParsedApiError(requestError));
    } finally {
      if (operationEpochRef.current === epoch) {
        saveInFlightRef.current = false;
        setSaving(false);
      }
    }
  }, [flags, loading, signalId]);

  const controlsDisabled = loading || saving || flags === null;
  const errorTitle = errorKind === 'load'
    ? t('decisionSignals.memoryLoadErrorTitle')
    : t('decisionSignals.memorySaveErrorTitle');

  return (
    <Section
      title={t('decisionSignals.memoryTitle')}
      description={t('decisionSignals.memoryDescription')}
      headingAs="h3"
      level="section"
      padding="sm"
      actions={(
        <div className="flex flex-wrap gap-2">
          {flags?.memorable ? (
            <Badge variant="info">{t('decisionSignals.memoryMemorable')}</Badge>
          ) : null}
          {flags?.ignored ? (
            <Badge variant="warning">{t('decisionSignals.memoryIgnored')}</Badge>
          ) : null}
          {flags && !flags.memorable && !flags.ignored ? (
            <Badge variant="default">{t('decisionSignals.memoryDefault')}</Badge>
          ) : null}
        </div>
      )}
    >
      <div className="space-y-3" aria-busy={loading || saving || undefined}>
        {error ? (
          <ApiErrorAlert
            error={{ ...error, title: errorTitle }}
            actionLabel={t('common.retry')}
            onAction={() => void loadFlags()}
          />
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                {t('decisionSignals.memoryMemorable')}
              </p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {t('decisionSignals.memoryMemorableDescription')}
              </p>
            </div>
            <Switch
              checked={flags?.memorable ?? false}
              disabled={controlsDisabled}
              aria-label={t('decisionSignals.memoryMemorable')}
              onCheckedChange={(next) => void updateFlag('memorable', next)}
            />
          </div>
          <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                {t('decisionSignals.memoryIgnored')}
              </p>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {t('decisionSignals.memoryIgnoredDescription')}
              </p>
            </div>
            <Switch
              checked={flags?.ignored ?? false}
              disabled={controlsDisabled}
              aria-label={t('decisionSignals.memoryIgnored')}
              onCheckedChange={(next) => void updateFlag('ignored', next)}
            />
          </div>
        </div>
        {flags?.memorable && flags.ignored ? (
          <InlineAlert
            variant="warning"
            message={t('decisionSignals.memoryIgnoredPrecedence')}
          />
        ) : null}
      </div>
    </Section>
  );
};
