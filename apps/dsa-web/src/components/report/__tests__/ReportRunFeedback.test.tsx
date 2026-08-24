// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH } from '../../../api/agentFeedback';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ReportRunFeedback } from '../ReportRunFeedback';

function renderFeedback(
  overrides: Partial<ComponentProps<typeof ReportRunFeedback>> = {},
) {
  const onDraftNoteChange = vi.fn();
  const onSubmitValue = vi.fn();
  render(
    <UiLanguageProvider>
      <ReportRunFeedback
        feedbackValue={null}
        draftNote=""
        onDraftNoteChange={onDraftNoteChange}
        onSubmitValue={onSubmitValue}
        {...overrides}
      />
    </UiLanguageProvider>,
  );
  return { onDraftNoteChange, onSubmitValue };
}

describe('ReportRunFeedback', () => {
  it('renders the empty state with four enabled ratings', () => {
    renderFeedback();
    expect(screen.getByRole('heading', { name: 'Analysis run feedback' })).toBeInTheDocument();
    expect(screen.getByText('No feedback yet')).toBeInTheDocument();
    for (const name of ['Useful', 'Partial', 'Wrong', 'Harmful']) {
      const button = screen.getByRole('button', { name });
      expect(button).toHaveAttribute('type', 'button');
      expect(button).toHaveAttribute('data-control', 'selection-chip');
      expect(button).toHaveAttribute('aria-pressed', 'false');
      expect(button).toBeEnabled();
      expect(button).toHaveClass('control-hit-target');
    }
    expect(screen.getByLabelText('Note (optional)')).toHaveValue('');
  });

  it('renders loading with disabled controls and no error live region', () => {
    renderFeedback({ isLoading: true });
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    expect(screen.queryByText('Feedback note was rejected.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Useful' })).toBeDisabled();
    expect(screen.getByLabelText('Note (optional)')).toBeDisabled();
  });

  it('marks the last successful value pressed and prefills the note', () => {
    renderFeedback({
      feedbackValue: 'useful',
      draftNote: 'Looks consistent with the tape.',
    });
    expect(screen.getByRole('button', { name: 'Useful' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Partial' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByLabelText('Note (optional)')).toHaveValue('Looks consistent with the tape.');
  });

  it('sends the current note when a different value is clicked', () => {
    const { onSubmitValue } = renderFeedback({
      feedbackValue: 'useful',
      draftNote: 'Looks consistent with the tape.',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Partial' }));
    expect(onSubmitValue).toHaveBeenCalledWith('partial');
  });

  it('sends an empty note when the textarea is empty and a value is clicked', () => {
    const { onSubmitValue } = renderFeedback({
      feedbackValue: 'useful',
      draftNote: '',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Wrong' }));
    expect(onSubmitValue).toHaveBeenCalledWith('wrong');
    expect(screen.getByLabelText('Note (optional)')).toHaveValue('');
  });

  it('re-presses the selected value to submit a note-only edit', () => {
    const { onSubmitValue } = renderFeedback({
      feedbackValue: 'useful',
      draftNote: 'Edited note',
    });
    const useful = screen.getByRole('button', { name: 'Useful' });
    expect(useful).toHaveAttribute('aria-pressed', 'true');
    useful.focus();
    expect(useful).toHaveFocus();
    fireEvent.click(useful);
    expect(onSubmitValue).toHaveBeenCalledWith('useful');
  });

  it('keeps the prior pressed value on error and does not claim saved', () => {
    renderFeedback({
      feedbackValue: 'useful',
      draftNote: 'stockpulse-agent-soul',
      errorMessage: 'Feedback note was rejected.',
    });
    expect(screen.getByRole('button', { name: 'Useful' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Feedback note was rejected.')).toHaveAttribute('aria-live', 'polite');
    expect(screen.queryByText('Saving feedback')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Note (optional)')).toHaveValue('stockpulse-agent-soul');
  });

  it('caps the note at 1000 characters and hides the 404 panel', () => {
    renderFeedback({ draftNote: 'x'.repeat(20) });
    expect(screen.getByLabelText('Note (optional)')).toHaveAttribute('maxLength', String(AGENT_RUN_FEEDBACK_NOTE_MAX_LENGTH));
    expect(screen.getByText('980 characters remaining')).toBeInTheDocument();

    const { container } = render(
      <UiLanguageProvider>
        <ReportRunFeedback
          hidden
          feedbackValue="useful"
          draftNote="hidden"
          onDraftNoteChange={() => undefined}
          onSubmitValue={() => undefined}
        />
      </UiLanguageProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('disables controls while saving and sets aria-busy on the group', () => {
    renderFeedback({ isSaving: true, feedbackValue: 'useful' });
    expect(screen.getByRole('group')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: 'Useful' })).toBeDisabled();
    expect(screen.getByLabelText('Note (optional)')).toBeDisabled();
  });
});
