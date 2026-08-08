import type React from 'react';
import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import { formatUiText } from '../../i18n/uiText';
import { Button, InlineAlert } from '../common';
import { ScreenAlertMessage } from './ScreenAlertMessage';
import type { ScreeningCapabilityState } from './screeningPageState';
import type { ScreeningText } from './screeningText';

export type ScreeningPageAlertsProps = {
  text: ScreeningText;
  capability: ScreeningCapabilityState;
  enabling: boolean;
  loading: boolean;
  error: string;
  taskMessage: string;
  activeTaskId: string | null;
  partialDegraded: boolean;
  llmDegraded: boolean;
  alertMessages: string[];
  screenMeta: AlphaSiftScreenResponse | null;
  candidatesCount: number;
  onEnable: () => void;
  onOpenDataSources: () => void;
};

export const ScreeningPageAlerts: React.FC<ScreeningPageAlertsProps> = ({
  text, capability, enabling, loading, error, taskMessage, activeTaskId,
  partialDegraded, llmDegraded, alertMessages, screenMeta, candidatesCount,
  onEnable, onOpenDataSources,
}) => (
  <>
    {capability === 'disabled' ? (
      <InlineAlert variant="info" title={text.notEnabledTitle} message={text.notEnabledMessage}
        action={<Button variant="primary" size="default" isLoading={enabling} loadingText={text.enabling} onClick={onEnable}>{text.enable}</Button>} />
    ) : null}
    {capability === 'unavailable' ? (
      <InlineAlert variant="warning" title={text.unavailableTitle} message={text.unavailableMessage}
        action={<Button variant="secondary" size="default" onClick={onOpenDataSources}>{text.openDataSources}</Button>} />
    ) : null}
    <InlineAlert variant="warning" title={text.riskTitle} message={text.riskMessage} />
    {loading ? (
      <InlineAlert variant="info" title={text.taskRunningTitle}
        message={`${taskMessage || text.runningTask}. ${text.taskId}: ${activeTaskId ? activeTaskId.slice(0, 12) : '-'}`} />
    ) : null}
    {error ? <InlineAlert variant="danger" title={text.callFailed} message={error} /> : null}
    {partialDegraded ? (
      <InlineAlert variant="warning" title={llmDegraded ? text.llmDegraded : text.alphaSiftNotice}
        message={(
          <div className="space-y-1">
            <p>{formatUiText(text.degradedResultsHint, {
              snapshot: screenMeta?.snapshotCount ?? '-',
              filtered: screenMeta?.afterFilterCount ?? '-',
              candidates: screenMeta?.candidateCount ?? candidatesCount,
            })}</p>
            {alertMessages.length > 0 ? <ScreenAlertMessage messages={alertMessages} /> : null}
          </div>
        )} />
    ) : screenMeta && alertMessages.length > 0 ? (
      <InlineAlert variant={llmDegraded ? 'warning' : 'info'} title={llmDegraded ? text.llmDegraded : text.alphaSiftNotice}
        message={<ScreenAlertMessage messages={alertMessages} />} />
    ) : null}
  </>
);
