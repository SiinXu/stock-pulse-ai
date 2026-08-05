// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Button,
  Drawer,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  DecisionSignalFeedbackItem,
  DecisionSignalFeedbackValue,
  DecisionSignalItem,
  DecisionSignalOutcomeItem,
  DecisionSignalStatus,
} from '../../types/decisionSignals';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import { DecisionSignalDetails } from './DecisionSignalDisplay';
import { DecisionSignalMemoryControls } from './DecisionSignalMemoryControls';
import {
  STATUS_ACTION_CONFIRM_KEYS,
  STATUS_ACTION_LABEL_KEYS,
  STATUS_ACTIONS,
  type SelectedSignal,
} from './decisionSignalsPageModel';

export type DecisionSignalDetailDrawerProps = {
  selected: SelectedSignal | null;
  onClose: () => void;
  statusError: ParsedApiError | null;
  onDismissStatusError: () => void;
  reassessPanel: React.ReactNode;
  outcomes: DecisionSignalOutcomeItem[];
  outcomesLoading: boolean;
  outcomesError: ParsedApiError | null;
  feedback: DecisionSignalFeedbackItem | null;
  feedbackLoading: boolean;
  feedbackSaving: boolean;
  feedbackError: ParsedApiError | null;
  onFeedbackSubmit: (feedbackValue: DecisionSignalFeedbackValue) => void;
  statusUpdating: boolean;
  onRequestStatusChange: (
    item: DecisionSignalItem,
    status: Extract<DecisionSignalStatus, 'closed' | 'invalidated' | 'archived'>,
    message: string,
  ) => void;
};

export const DecisionSignalDetailDrawer: React.FC<DecisionSignalDetailDrawerProps> = ({
  selected,
  onClose,
  statusError,
  onDismissStatusError,
  reassessPanel,
  outcomes,
  outcomesLoading,
  outcomesError,
  feedback,
  feedbackLoading,
  feedbackSaving,
  feedbackError,
  onFeedbackSubmit,
  statusUpdating,
  onRequestStatusChange,
}) => {
  const { t } = useUiLanguage();

  return (
    <Drawer
      isOpen={Boolean(selected)}
      onClose={onClose}
      title={t('decisionSignals.detailTitle')}
      variant="detail"
      size="wide"
    >
      {selected ? (
        <div className="space-y-4">
          {statusError ? (
            <ApiErrorAlert error={statusError} onDismiss={onDismissStatusError} />
          ) : null}
          {reassessPanel}
          <DecisionSignalMemoryControls
            key={selected.item.id}
            signalId={selected.item.id}
          />
          <DecisionSignalDetails
            item={selected.item}
            outcomes={outcomes}
            outcomesLoading={outcomesLoading}
            outcomesError={outcomesError?.message ?? null}
            feedback={feedback}
            feedbackLoading={feedbackLoading}
            feedbackSaving={feedbackSaving}
            feedbackError={feedbackError?.message ?? null}
            onFeedbackSubmit={onFeedbackSubmit}
            actions={(
              <>
                {selected.item.sourceReportId ? (
                  <Link
                    to={buildAnalysisWorkbenchHref({
                      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
                      recordId: selected.item.sourceReportId,
                      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
                      runFlowRecordId: selected.item.sourceReportId,
                      stock: selected.item.stockCode,
                    })}
                    data-control="navigation-link"
                    className="control-hit-target inline-flex min-h-7 min-w-0 max-w-full items-center gap-1.5 px-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    {t('decisionSignals.reassessSource', { id: selected.item.sourceReportId })}
                  </Link>
                ) : null}
                {STATUS_ACTIONS.map((status) => (
                  <Button
                    key={status}
                    type="button"
                    variant="secondary"
                    size="comfortable"
                    className="text-xs"
                    onClick={() => {
                      onRequestStatusChange(
                        selected.item,
                        status,
                        t(STATUS_ACTION_CONFIRM_KEYS[status]),
                      );
                    }}
                    disabled={statusUpdating || selected.item.status === status}
                  >
                    {t(STATUS_ACTION_LABEL_KEYS[status])}
                  </Button>
                ))}
              </>
            )}
          />
        </div>
      ) : null}
    </Drawer>
  );
};
