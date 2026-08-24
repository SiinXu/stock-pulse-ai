// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import {
  AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH,
  AGENT_RUN_FEEDBACK_VALUES,
  type AgentRunFeedbackValue,
} from '../../api/agentFeedback';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Section, SelectionChip, Textarea } from '../common';

export type ReportRunFeedbackProps = {
  feedbackValue: AgentRunFeedbackValue | null;
  draftNote: string;
  isLoading?: boolean;
  isSaving?: boolean;
  errorMessage?: string | null;
  hidden?: boolean;
  onDraftNoteChange: (note: string) => void;
  onSubmitValue: (value: AgentRunFeedbackValue) => void;
};

const VALUE_LABEL_KEYS = {
  useful: 'reportRunFeedback.useful',
  partial: 'reportRunFeedback.partial',
  wrong: 'reportRunFeedback.wrong',
  harmful: 'reportRunFeedback.harmful',
} as const;

const HEADING_ID = 'report-run-feedback-heading';

export const ReportRunFeedback: React.FC<ReportRunFeedbackProps> = ({
  feedbackValue,
  draftNote,
  isLoading = false,
  isSaving = false,
  errorMessage = null,
  hidden = false,
  onDraftNoteChange,
  onSubmitValue,
}) => {
  const { t } = useUiLanguage();
  if (hidden) {
    return null;
  }

  const controlsDisabled = isLoading || isSaving;
  const remaining = Math.max(0, AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH - draftNote.length);
  const statusText = isLoading
    ? `${t('common.loading')}...`
    : (feedbackValue ? null : t('reportRunFeedback.empty'));

  return (
    <Section
      title={t('reportRunFeedback.title')}
      description={t('reportRunFeedback.help')}
      headingAs="h3"
      headingId={HEADING_ID}
      level="section"
      padding="sm"
      data-testid="report-run-feedback"
    >
      <div className="flex flex-col gap-3">
        <div
          role="group"
          aria-labelledby={HEADING_ID}
          aria-busy={isSaving || undefined}
          className="flex flex-wrap gap-2"
        >
          {AGENT_RUN_FEEDBACK_VALUES.map((value) => (
            <SelectionChip
              key={value}
              label={t(VALUE_LABEL_KEYS[value])}
              selected={feedbackValue === value}
              disabled={controlsDisabled}
              showSelectionIndicator={false}
              onClick={() => onSubmitValue(value)}
            />
          ))}
        </div>

        {statusText ? (
          <p className="text-sm text-secondary-text">{statusText}</p>
        ) : null}

        {errorMessage ? (
          <p aria-live="polite" className="text-sm text-danger">{errorMessage}</p>
        ) : isSaving ? (
          <p aria-live="polite" className="text-sm text-secondary-text">
            {t('reportRunFeedback.saving')}
          </p>
        ) : (
          <p aria-live="polite" className="sr-only" />
        )}

        <Textarea
          label={t('reportRunFeedback.noteLabel')}
          hint={t('reportRunFeedback.noteRemaining', { count: remaining })}
          placeholder={t('reportRunFeedback.notePlaceholder')}
          value={draftNote}
          maxLength={AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH}
          disabled={controlsDisabled}
          onChange={(event) => onDraftNoteChange(event.target.value)}
        />
      </div>
    </Section>
  );
};
