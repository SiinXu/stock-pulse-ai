import type React from 'react';
import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import type { ParsedApiError } from '../../api/error';
import { formatUiText } from '../../i18n/uiText';
import { Button, InlineAlert } from '../common';
import { ScreenAlertMessage } from './ScreenAlertMessage';
import type { ScreeningDegradationReasons } from './screeningDegradation';
import type {
  ScreeningAttemptState,
  ScreeningCapabilityState,
} from './screeningPageState';
import { isScreeningAttemptLoading } from './screeningPageState';
import type { ScreeningText } from './screeningText';

export type ScreeningPageAlertsProps = {
  text: ScreeningText;
  capability: ScreeningCapabilityState;
  capabilityError: ParsedApiError | null;
  attemptState: ScreeningAttemptState;
  enabling: boolean;
  capabilityActionError: string;
  error: string;
  taskMessage: string;
  activeTaskId: string | null;
  degradationReasons: ScreeningDegradationReasons;
  attemptResult: AlphaSiftScreenResponse | null;
  candidatesCount: number;
  showingLastGood: boolean;
  canRetryScreen: boolean;
  onEnable: () => void;
  onOpenDataSources: () => void;
  onRetryStatus: () => void;
  onAdminLogin: () => void;
  onRetryScreen: () => void;
};

const DegradationAlert: React.FC<{
  title: string;
  message: React.ReactNode;
  reasons: string[];
}> = ({ title, message, reasons }) => (
  <InlineAlert
    variant="warning"
    title={title}
    message={(
      <div className="space-y-1">
        <p>{message}</p>
        {reasons.length > 0 ? <ScreenAlertMessage messages={reasons} /> : null}
      </div>
    )}
  />
);

const ScreeningPageAlerts: React.FC<ScreeningPageAlertsProps> = ({
  text,
  capability,
  capabilityError,
  attemptState,
  enabling,
  capabilityActionError,
  error,
  taskMessage,
  activeTaskId,
  degradationReasons,
  attemptResult,
  candidatesCount,
  showingLastGood,
  canRetryScreen,
  onEnable,
  onOpenDataSources,
  onRetryStatus,
  onAdminLogin,
  onRetryScreen,
}) => {
  const loading = isScreeningAttemptLoading(attemptState);
  const statusNeedsLogin = capabilityError?.status === 401
    || capabilityError?.status === 403
    || capabilityError?.code === 'unauthorized';

  return (
    <>
      {capability === 'disabled' ? (
        <InlineAlert
          variant="info"
          title={text.notEnabledTitle}
          message={text.notEnabledMessage}
          action={(
            <Button
              variant="primary"
              size="default"
              isLoading={enabling}
              loadingText={text.enabling}
              onClick={onEnable}
            >
              {text.enable}
            </Button>
          )}
        />
      ) : null}
      {capability === 'adapter_unavailable' ? (
        <InlineAlert
          variant="warning"
          title={text.unavailableTitle}
          message={text.unavailableMessage}
          action={(
            <Button variant="secondary" size="default" onClick={onOpenDataSources}>
              {text.openDataSources}
            </Button>
          )}
        />
      ) : null}
      {capability === 'status_error' && capabilityError ? (
        <InlineAlert
          variant="danger"
          title={text.statusCheckFailedTitle}
          message={capabilityError.message}
          action={(
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="default" onClick={onRetryStatus}>
                {text.retryStatus}
              </Button>
              {statusNeedsLogin ? (
                <Button variant="secondary" size="default" onClick={onAdminLogin}>
                  {text.adminLogin}
                </Button>
              ) : null}
            </div>
          )}
        />
      ) : null}
      {capabilityActionError ? (
        <InlineAlert
          variant="danger"
          title={text.callFailed}
          message={capabilityActionError}
        />
      ) : null}
      <InlineAlert variant="warning" title={text.riskTitle} message={text.riskMessage} />
      {loading ? (
        <InlineAlert
          variant="info"
          title={text.taskRunningTitle}
          message={`${taskMessage || text.runningTask}. ${text.taskId}: ${activeTaskId ? activeTaskId.slice(0, 12) : '-'}`}
        />
      ) : null}
      {error ? (
        <InlineAlert
          variant={attemptState === 'recoverable_poll_error' ? 'warning' : 'danger'}
          title={text.callFailed}
          message={error}
          action={canRetryScreen && attemptState !== 'recoverable_poll_error' ? (
            <Button variant="primary" size="default" onClick={onRetryScreen}>
              {text.retry}
            </Button>
          ) : undefined}
        />
      ) : null}
      {showingLastGood ? (
        <InlineAlert
          variant="warning"
          title={text.showingLastGoodTitle}
          message={text.showingLastGoodMessage}
        />
      ) : null}
      {degradationReasons.source.length > 0 ? (
        <DegradationAlert
          title={text.sourceDegradedTitle}
          message={formatUiText(text.degradedResultsHint, {
            snapshot: attemptResult?.snapshotCount ?? '-',
            filtered: attemptResult?.afterFilterCount ?? '-',
            candidates: attemptResult?.candidateCount ?? candidatesCount,
          })}
          reasons={degradationReasons.source}
        />
      ) : null}
      {degradationReasons.llm.length > 0 ? (
        <DegradationAlert
          title={text.llmDegraded}
          message={text.llmDegradedMessage}
          reasons={degradationReasons.llm}
        />
      ) : null}
      {degradationReasons.enrichment.length > 0 ? (
        <DegradationAlert
          title={text.enrichmentDegradedTitle}
          message={text.enrichmentDegradedMessage}
          reasons={degradationReasons.enrichment}
        />
      ) : null}
      {degradationReasons.general.length > 0 ? (
        <DegradationAlert
          title={text.generalDegradedTitle}
          message={text.generalDegradedMessage}
          reasons={degradationReasons.general}
        />
      ) : null}
    </>
  );
};

export default ScreeningPageAlerts;
