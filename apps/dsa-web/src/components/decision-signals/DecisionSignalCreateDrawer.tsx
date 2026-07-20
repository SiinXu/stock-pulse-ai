import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PlusCircle, RotateCcw, ShieldCheck } from 'lucide-react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Button,
  Drawer,
  Field,
  InlineAlert,
  Input,
  Select,
  Surface,
  Textarea,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import { normalizeStockCode } from '../../utils/stockCode';
import type { DecisionSignalMutationResponse } from '../../types/decisionSignals';
import {
  EMPTY_MANUAL_SIGNAL_DRAFT,
  MANUAL_ACTION_OPTIONS,
  MANUAL_HORIZON_OPTIONS,
  MANUAL_MARKET_OPTIONS,
  MANUAL_PHASE_OPTIONS,
  MANUAL_PROFILE_OPTIONS,
  MANUAL_SIGNAL_TRIGGER_SOURCE,
  buildManualSignalPayload,
  hasManualSignalErrors,
  manualSignalMayInvalidateOpposite,
  validateManualSignalDraft,
  type ManualSignalDraft,
  type ManualSignalErrorCode,
  type ManualSignalErrorField,
} from './manualSignalDraft';

interface DecisionSignalCreateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  draft: ManualSignalDraft;
  onDraftChange: (draft: ManualSignalDraft) => void;
  onCreated: (result: DecisionSignalMutationResponse) => void;
}

const ERROR_MESSAGE_KEYS: Record<ManualSignalErrorCode, UiTextKey> = {
  required: 'decisionSignals.create.error.required',
  confidenceRange: 'decisionSignals.create.error.confidenceRange',
  positive: 'decisionSignals.create.error.positive',
  entryOrder: 'decisionSignals.create.error.entryOrder',
  invalidDate: 'decisionSignals.create.error.invalidDate',
};

function previewValue(raw: string): string {
  const trimmed = raw.trim();
  return trimmed ? trimmed : '-';
}

export const DecisionSignalCreateDrawer: React.FC<DecisionSignalCreateDrawerProps> = ({
  isOpen,
  onClose,
  draft,
  onDraftChange,
  onCreated,
}) => {
  const { t } = useUiLanguage();
  const actionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);
  const [submitting, setSubmitting] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [result, setResult] = useState<DecisionSignalMutationResponse | null>(null);
  const [submitError, setSubmitError] = useState<ParsedApiError | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const errors = useMemo(() => validateManualSignalDraft(draft), [draft]);

  const setField = useCallback(
    <K extends keyof ManualSignalDraft>(key: K, value: ManualSignalDraft[K]) => {
      onDraftChange({ ...draft, [key]: value });
    },
    [draft, onDraftChange],
  );

  const fieldError = useCallback(
    (field: ManualSignalErrorField): string | undefined => {
      if (!showErrors) return undefined;
      const code = errors[field];
      return code ? t(ERROR_MESSAGE_KEYS[code]) : undefined;
    },
    [errors, showErrors, t],
  );

  const handleReset = useCallback(() => {
    onDraftChange({ ...EMPTY_MANUAL_SIGNAL_DRAFT });
    setShowErrors(false);
    setResult(null);
    setSubmitError(null);
  }, [onDraftChange]);

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (submitting) return;
      const validation = validateManualSignalDraft(draft);
      if (hasManualSignalErrors(validation)) {
        setShowErrors(true);
        return;
      }
      setSubmitting(true);
      setSubmitError(null);
      setResult(null);
      try {
        const response = await decisionSignalsApi.create(buildManualSignalPayload(draft));
        if (!mountedRef.current) return;
        setResult(response);
        onCreated(response);
        if (response.created) {
          onDraftChange({ ...EMPTY_MANUAL_SIGNAL_DRAFT });
          setShowErrors(false);
        }
      } catch (err) {
        if (!mountedRef.current) return;
        setSubmitError(getParsedApiError(err));
      } finally {
        if (mountedRef.current) setSubmitting(false);
      }
    },
    [draft, onCreated, onDraftChange, submitting],
  );

  const marketOptions = useMemo(
    () => MANUAL_MARKET_OPTIONS.map((market) => ({
      value: market,
      label: t(`decisionSignals.market.${market}` as UiTextKey),
    })),
    [t],
  );
  const actionOptions = useMemo(
    () => MANUAL_ACTION_OPTIONS.map((action) => ({ value: action, label: actionLabels[action] })),
    [actionLabels],
  );
  const horizonOptions = useMemo(
    () => [
      { value: '', label: t('decisionSignals.create.optionNone') },
      ...MANUAL_HORIZON_OPTIONS.map((horizon) => ({
        value: horizon,
        label: t(`decisionSignals.horizon.${horizon}` as UiTextKey),
      })),
    ],
    [t],
  );
  const phaseOptions = useMemo(
    () => [
      { value: '', label: t('decisionSignals.create.optionAuto') },
      ...MANUAL_PHASE_OPTIONS.map((phase) => ({
        value: phase,
        label: t(`decisionSignals.marketPhase.${phase}` as UiTextKey),
      })),
    ],
    [t],
  );
  const profileOptions = useMemo(
    () => [
      { value: '', label: t('decisionSignals.create.optionDefault') },
      ...MANUAL_PROFILE_OPTIONS.map((profile) => ({
        value: profile,
        label: t(`decisionSignals.profile.${profile}` as UiTextKey),
      })),
    ],
    [t],
  );

  const previewCode = normalizeStockCode(draft.stockCode.trim());
  const previewActionLabel = draft.action ? actionLabels[draft.action] : '-';
  const previewMarketLabel = draft.market ? t(`decisionSignals.market.${draft.market}` as UiTextKey) : '-';
  const previewReady = Boolean(previewCode && draft.market && draft.action);

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={t('decisionSignals.create.title')}
      description={t('decisionSignals.create.description')}
      variant="detail"
      size="wide"
      closeDisabled={submitting}
    >
      <form className="space-y-6" onSubmit={handleSubmit} noValidate>
        <Surface level="section" className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs text-secondary-text">
          <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
          <span>
            {t('decisionSignals.create.sourceFixed', {
              source: t('decisionSignals.sourceType.manual'),
              trigger: MANUAL_SIGNAL_TRIGGER_SOURCE,
            })}
          </span>
        </Surface>

        <section className="space-y-3" aria-labelledby="manual-signal-basics">
          <h3 id="manual-signal-basics" className="text-sm font-semibold text-foreground">
            {t('decisionSignals.create.sectionBasics')}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t('decisionSignals.stockCode')}
              value={draft.stockCode}
              onChange={(event) => setField('stockCode', event.target.value)}
              placeholder={t('decisionSignals.latestPlaceholder')}
              error={fieldError('stockCode')}
              autoComplete="off"
              spellCheck={false}
            />
            <Input
              label={t('decisionSignals.create.stockName')}
              value={draft.stockName}
              onChange={(event) => setField('stockName', event.target.value)}
              maxLength={64}
              autoComplete="off"
            />
            <Field controlId="manual-signal-market" label={t('decisionSignals.market')} error={fieldError('market')}>
              <Select
                id="manual-signal-market"
                className="w-full"
                value={draft.market}
                onChange={(value) => setField('market', value as ManualSignalDraft['market'])}
                options={marketOptions}
                ariaLabel={t('decisionSignals.market')}
                error={Boolean(fieldError('market'))}
              />
            </Field>
            <Field controlId="manual-signal-action" label={t('decisionSignals.action')} error={fieldError('action')}>
              <Select
                id="manual-signal-action"
                className="w-full"
                value={draft.action}
                onChange={(value) => setField('action', value as ManualSignalDraft['action'])}
                options={actionOptions}
                ariaLabel={t('decisionSignals.action')}
                error={Boolean(fieldError('action'))}
              />
            </Field>
            <Input
              label={t('decisionSignals.confidence')}
              value={draft.confidence}
              onChange={(event) => setField('confidence', event.target.value)}
              inputMode="decimal"
              placeholder="0 - 1"
              hint={t('decisionSignals.create.confidenceHint')}
              error={fieldError('confidence')}
            />
            <Field controlId="manual-signal-horizon" label={t('decisionSignals.horizon')}>
              <Select
                id="manual-signal-horizon"
                className="w-full"
                value={draft.horizon}
                onChange={(value) => setField('horizon', value as ManualSignalDraft['horizon'])}
                options={horizonOptions}
                ariaLabel={t('decisionSignals.horizon')}
              />
            </Field>
            <Field controlId="manual-signal-phase" label={t('decisionSignals.marketPhase')}>
              <Select
                id="manual-signal-phase"
                className="w-full"
                value={draft.marketPhase}
                onChange={(value) => setField('marketPhase', value as ManualSignalDraft['marketPhase'])}
                options={phaseOptions}
                ariaLabel={t('decisionSignals.marketPhase')}
              />
            </Field>
            <Field controlId="manual-signal-profile" label={t('decisionSignals.profile')}>
              <Select
                id="manual-signal-profile"
                className="w-full"
                value={draft.decisionProfile}
                onChange={(value) => setField('decisionProfile', value as ManualSignalDraft['decisionProfile'])}
                options={profileOptions}
                ariaLabel={t('decisionSignals.profile')}
              />
            </Field>
          </div>
        </section>

        <section className="space-y-3" aria-labelledby="manual-signal-plan">
          <h3 id="manual-signal-plan" className="text-sm font-semibold text-foreground">
            {t('decisionSignals.create.sectionPlan')}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t('decisionSignals.create.entryLow')}
              value={draft.entryLow}
              onChange={(event) => setField('entryLow', event.target.value)}
              inputMode="decimal"
              error={fieldError('entryLow')}
            />
            <Input
              label={t('decisionSignals.create.entryHigh')}
              value={draft.entryHigh}
              onChange={(event) => setField('entryHigh', event.target.value)}
              inputMode="decimal"
              error={fieldError('entryHigh')}
            />
            <Input
              label={t('decisionSignals.stopLoss')}
              value={draft.stopLoss}
              onChange={(event) => setField('stopLoss', event.target.value)}
              inputMode="decimal"
              error={fieldError('stopLoss')}
            />
            <Input
              label={t('decisionSignals.targetPrice')}
              value={draft.targetPrice}
              onChange={(event) => setField('targetPrice', event.target.value)}
              inputMode="decimal"
              error={fieldError('targetPrice')}
            />
            <Input
              type="date"
              label={t('decisionSignals.expiresAt')}
              value={draft.expiresAt}
              onChange={(event) => setField('expiresAt', event.target.value)}
              error={fieldError('expiresAt')}
              fieldClassName="sm:col-span-2"
            />
          </div>
          <Textarea
            label={t('decisionSignals.invalidation')}
            value={draft.invalidation}
            onChange={(event) => setField('invalidation', event.target.value)}
            rows={2}
          />
          <Textarea
            label={t('decisionSignals.watchConditions')}
            value={draft.watchConditions}
            onChange={(event) => setField('watchConditions', event.target.value)}
            rows={2}
          />
        </section>

        <section className="space-y-3" aria-labelledby="manual-signal-rationale">
          <h3 id="manual-signal-rationale" className="text-sm font-semibold text-foreground">
            {t('decisionSignals.create.sectionRationale')}
          </h3>
          <Textarea
            label={t('decisionSignals.reason')}
            value={draft.reason}
            onChange={(event) => setField('reason', event.target.value)}
            rows={3}
          />
          <Textarea
            label={t('decisionSignals.riskSummary')}
            value={draft.riskSummary}
            onChange={(event) => setField('riskSummary', event.target.value)}
            rows={2}
          />
          <Textarea
            label={t('decisionSignals.catalystSummary')}
            value={draft.catalystSummary}
            onChange={(event) => setField('catalystSummary', event.target.value)}
            rows={2}
          />
          <Textarea
            label={t('decisionSignals.evidence')}
            value={draft.evidence}
            onChange={(event) => setField('evidence', event.target.value)}
            rows={2}
            hint={t('decisionSignals.create.evidenceHint')}
          />
        </section>

        <Surface
          as="section"
          level="section"
          padding="sm"
          className="space-y-2"
          aria-labelledby="manual-signal-preview"
        >
          <h3 id="manual-signal-preview" className="text-sm font-semibold text-foreground">
            {t('decisionSignals.create.previewTitle')}
          </h3>
          {previewReady ? (
            <dl className="grid gap-x-4 gap-y-2 text-xs sm:grid-cols-2">
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.stockCode')}</dt>
                <dd className="font-medium text-foreground">{previewCode}{draft.stockName.trim() ? ` · ${draft.stockName.trim()}` : ''}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.market')}</dt>
                <dd className="font-medium text-foreground">{previewMarketLabel}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.action')}</dt>
                <dd className="font-medium text-foreground">{previewActionLabel}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.confidence')}</dt>
                <dd className="font-medium text-foreground">{previewValue(draft.confidence)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.entryRange')}</dt>
                <dd className="font-medium text-foreground">
                  {draft.entryLow.trim() || draft.entryHigh.trim()
                    ? `${previewValue(draft.entryLow)} ~ ${previewValue(draft.entryHigh)}`
                    : '-'}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.stopLoss')}</dt>
                <dd className="font-medium text-foreground">{previewValue(draft.stopLoss)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.targetPrice')}</dt>
                <dd className="font-medium text-foreground">{previewValue(draft.targetPrice)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-secondary-text">{t('decisionSignals.expiresAt')}</dt>
                <dd className="font-medium text-foreground">{previewValue(draft.expiresAt)}</dd>
              </div>
              <div className="flex justify-between gap-2 sm:col-span-2">
                <dt className="text-secondary-text">{t('decisionSignals.source')}</dt>
                <dd className="font-medium text-foreground">
                  {t('decisionSignals.sourceType.manual')} · {MANUAL_SIGNAL_TRIGGER_SOURCE}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-xs text-secondary-text">{t('decisionSignals.create.previewEmpty')}</p>
          )}
        </Surface>

        {result ? (
          <InlineAlert
            variant={result.created ? 'success' : 'info'}
            title={t(result.created ? 'decisionSignals.create.successTitle' : 'decisionSignals.create.dedupTitle')}
            message={
              result.created
                ? manualSignalMayInvalidateOpposite(result.item.action)
                  ? `${t('decisionSignals.create.success', { id: result.item.id })} ${t('decisionSignals.create.invalidationNote')}`
                  : t('decisionSignals.create.success', { id: result.item.id })
                : t('decisionSignals.create.dedup', { id: result.item.id })
            }
          />
        ) : null}
        {submitError ? <ApiErrorAlert error={submitError} /> : null}

        <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-4">
          <Button
            type="button"
            variant="ghost"
            size="comfortable"
            onClick={handleReset}
            disabled={submitting}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {t('common.clear')}
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="primary"
            isLoading={submitting}
            loadingText={t('decisionSignals.create.submitting')}
          >
            <PlusCircle className="h-4 w-4" aria-hidden="true" />
            {t('decisionSignals.create.button')}
          </Button>
        </div>
      </form>
    </Drawer>
  );
};
